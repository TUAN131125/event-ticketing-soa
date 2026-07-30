"""Transactional Identity use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.domain.entities import RoleChange, TokenPair, UserView
from app.domain.enums import AuditResult, RoleAction, RoleName, UserStatus
from app.domain.exceptions import (
    AccountDisabled,
    AccountLocked,
    EmailAlreadyExists,
    Forbidden,
    IdentityError,
    InvalidCredentials,
    InvalidRefreshToken,
    RateLimited,
    RefreshTokenReuseDetected,
    RoleNotFound,
    TokenRevoked,
    Unauthenticated,
    UserNotFound,
)
from app.domain.rules import normalize_email, validate_password
from app.domain.value_objects import Principal, RequestContext
from app.infrastructure.database.models import (
    RefreshSessionModel,
    RoleModel,
    UserModel,
    UserRoleModel,
)
from app.infrastructure.database.repositories import (
    consume_login_attempt,
    database_now,
    reset_login_attempts,
    revoke_family,
    roles_for_user,
    to_user_view,
    write_audit,
)
from app.observability.metrics import AUTH_EVENTS
from app.security.passwords import PasswordService
from app.security.tokens import TokenService


@dataclass(frozen=True, slots=True)
class LoginOutcome:
    token_pair: TokenPair
    session_id: str


class IdentityService:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        password_service: PasswordService,
        token_service: TokenService,
    ) -> None:
        self.settings = settings
        self._sessions = session_factory
        self.passwords = password_service
        self.tokens = token_service

    def register(self, email: str, password: str, context: RequestContext) -> UserView:
        display_email, normalized_email = normalize_email(email)
        validate_password(password)
        password_hash = self.passwords.hash(password)
        pending_error: IdentityError | None = None
        created: UserView | None = None
        try:
            with self._sessions() as session, session.begin():
                existing = session.scalar(
                    select(UserModel).where(
                        UserModel.normalized_email == normalized_email
                    )
                )
                if existing is not None:
                    write_audit(
                        session,
                        context,
                        action="REGISTER",
                        result=AuditResult.FAILURE,
                        reason="EMAIL_ALREADY_EXISTS",
                        target_user_id=existing.user_id,
                    )
                    pending_error = EmailAlreadyExists()
                else:
                    user = UserModel(
                        user_id=str(uuid.uuid4()),
                        email=display_email,
                        normalized_email=normalized_email,
                        password_hash=password_hash,
                        status=UserStatus.ACTIVE,
                        token_version=1,
                        failed_login_count=0,
                    )
                    session.add(user)
                    session.flush()
                    session.add(
                        UserRoleModel(
                            user_id=user.user_id,
                            role_name=RoleName.CUSTOMER,
                            assigned_by=None,
                        )
                    )
                    session.flush()
                    write_audit(
                        session,
                        context,
                        action="REGISTER",
                        result=AuditResult.SUCCESS,
                        target_user_id=user.user_id,
                    )
                    created = to_user_view(session, user)
        except IntegrityError as exc:
            self._audit_registration_conflict(normalized_email, context)
            raise EmailAlreadyExists() from exc
        if pending_error is not None:
            AUTH_EVENTS.labels("register", pending_error.code).inc()
            raise pending_error
        if created is None:
            raise RuntimeError("Registration completed without a user")
        AUTH_EVENTS.labels("register", "success").inc()
        return created

    def _audit_registration_conflict(
        self, normalized_email: str, context: RequestContext
    ) -> None:
        with self._sessions() as session, session.begin():
            existing_id = session.scalar(
                select(UserModel.user_id).where(
                    UserModel.normalized_email == normalized_email
                )
            )
            write_audit(
                session,
                context,
                action="REGISTER",
                result=AuditResult.FAILURE,
                reason="EMAIL_ALREADY_EXISTS",
                target_user_id=existing_id,
            )

    def login(self, email: str, password: str, context: RequestContext) -> LoginOutcome:
        _, normalized_email = normalize_email(email)
        pending_error: IdentityError | None = None
        outcome: LoginOutcome | None = None
        with self._sessions() as session, session.begin():
            retry_after = consume_login_attempt(
                session,
                subject=normalized_email,
                client_ip=context.client_ip,
                window_seconds=self.settings.login_window_seconds,
                limit=self.settings.login_rate_limit,
            )
            if retry_after is not None:
                self.passwords.verify(self.passwords.dummy_hash, password)
                write_audit(
                    session,
                    context,
                    action="LOGIN",
                    result=AuditResult.FAILURE,
                    reason="RATE_LIMITED",
                )
                pending_error = RateLimited(retry_after)
            else:
                user = session.scalar(
                    select(UserModel)
                    .where(UserModel.normalized_email == normalized_email)
                    .with_for_update()
                )
                encoded_hash = (
                    user.password_hash
                    if user is not None
                    else self.passwords.dummy_hash
                )
                password_valid = self.passwords.verify(encoded_hash, password)
                now = database_now(session)
                if user is not None and user.locked_until is not None:
                    if user.locked_until > now:
                        retry = int((user.locked_until - now).total_seconds())
                        write_audit(
                            session,
                            context,
                            action="LOGIN",
                            result=AuditResult.FAILURE,
                            reason="ACCOUNT_LOCKED",
                            target_user_id=user.user_id,
                        )
                        pending_error = AccountLocked(retry)
                    else:
                        user.locked_until = None
                        user.failed_login_count = 0
                if pending_error is None and (user is None or not password_valid):
                    if user is not None:
                        user.failed_login_count += 1
                        user.updated_at = now
                        if user.failed_login_count >= self.settings.lockout_threshold:
                            user.locked_until = now + timedelta(
                                seconds=self.settings.lockout_seconds
                            )
                    write_audit(
                        session,
                        context,
                        action="LOGIN",
                        result=AuditResult.FAILURE,
                        reason="INVALID_CREDENTIALS",
                        target_user_id=user.user_id if user else None,
                    )
                    pending_error = InvalidCredentials()
                if (
                    pending_error is None
                    and user is not None
                    and user.status != UserStatus.ACTIVE
                ):
                    write_audit(
                        session,
                        context,
                        action="LOGIN",
                        result=AuditResult.FAILURE,
                        reason="ACCOUNT_DISABLED",
                        target_user_id=user.user_id,
                    )
                    pending_error = AccountDisabled()
                if pending_error is None and user is not None:
                    if self.passwords.needs_rehash(user.password_hash):
                        user.password_hash = self.passwords.hash(password)
                    user.failed_login_count = 0
                    user.locked_until = None
                    user.last_login_at = now
                    user.updated_at = now
                    reset_login_attempts(
                        session,
                        subject=normalized_email,
                        client_ip=context.client_ip,
                    )
                    roles = roles_for_user(session, user.user_id)
                    outcome = self._new_token_pair(
                        session,
                        user,
                        roles,
                        context,
                        now=now,
                        family_id=str(uuid.uuid4()),
                        parent_session_id=None,
                    )
                    write_audit(
                        session,
                        context,
                        action="LOGIN",
                        result=AuditResult.SUCCESS,
                        target_user_id=user.user_id,
                        metadata={"sessionId": outcome.session_id},
                    )
        if pending_error is not None:
            AUTH_EVENTS.labels("login", pending_error.code).inc()
            raise pending_error
        if outcome is None:
            raise RuntimeError("Login completed without an outcome")
        AUTH_EVENTS.labels("login", "success").inc()
        AUTH_EVENTS.labels("token_issued", "success").inc()
        return outcome

    def _new_token_pair(
        self,
        session: Session,
        user: UserModel,
        roles: tuple[str, ...],
        context: RequestContext,
        *,
        now: datetime,
        family_id: str,
        parent_session_id: str | None,
    ) -> LoginOutcome:
        raw_refresh = self.tokens.generate_refresh_token()
        refresh_session = RefreshSessionModel(
            session_id=str(uuid.uuid4()),
            user_id=user.user_id,
            token_hash=self.tokens.hash_refresh_token(raw_refresh),
            family_id=family_id,
            parent_session_id=parent_session_id,
            expires_at=now + timedelta(seconds=self.settings.refresh_token_ttl_seconds),
            user_agent_hash=self.tokens.user_agent_hash(context.user_agent),
            created_at=now,
        )
        session.add(refresh_session)
        session.flush()
        access_token = self.tokens.issue_access_token(
            user_id=user.user_id,
            roles=roles,
            token_version=user.token_version,
            now=now,
        )
        return LoginOutcome(
            token_pair=TokenPair(
                access_token=access_token,
                refresh_token=raw_refresh,
                access_expires_in=self.settings.access_token_ttl_seconds,
                refresh_expires_at=refresh_session.expires_at,
                user=to_user_view(session, user),
            ),
            session_id=refresh_session.session_id,
        )

    def refresh(self, raw_refresh_token: str, context: RequestContext) -> LoginOutcome:
        token_hash = self.tokens.hash_refresh_token(raw_refresh_token)
        pending_error: IdentityError | None = None
        outcome: LoginOutcome | None = None
        with self._sessions() as session, session.begin():
            current = session.scalar(
                select(RefreshSessionModel)
                .where(RefreshSessionModel.token_hash == token_hash)
                .with_for_update()
            )
            now = database_now(session)
            if current is None:
                write_audit(
                    session,
                    context,
                    action="REFRESH",
                    result=AuditResult.FAILURE,
                    reason="INVALID_REFRESH_TOKEN",
                )
                pending_error = InvalidRefreshToken()
            elif current.replaced_by_session_id is not None or (
                current.revoked_at is not None
                and current.revoke_reason in {"ROTATED", "REUSE_DETECTED"}
            ):
                revoke_family(
                    session,
                    current.family_id,
                    now=now,
                    reason="REUSE_DETECTED",
                )
                write_audit(
                    session,
                    context,
                    action="REFRESH",
                    result=AuditResult.FAILURE,
                    reason="REFRESH_TOKEN_REUSE_DETECTED",
                    target_user_id=current.user_id,
                    metadata={"familyId": current.family_id},
                )
                pending_error = RefreshTokenReuseDetected()
            elif current.revoked_at is not None or current.expires_at <= now:
                if current.revoked_at is None:
                    current.revoked_at = now
                    current.revoke_reason = "EXPIRED"
                write_audit(
                    session,
                    context,
                    action="REFRESH",
                    result=AuditResult.FAILURE,
                    reason="INVALID_REFRESH_TOKEN",
                    target_user_id=current.user_id,
                )
                pending_error = InvalidRefreshToken()
            else:
                user = session.scalar(
                    select(UserModel)
                    .where(UserModel.user_id == current.user_id)
                    .with_for_update()
                )
                if user is None:
                    pending_error = InvalidRefreshToken()
                elif user.status != UserStatus.ACTIVE:
                    revoke_family(
                        session,
                        current.family_id,
                        now=now,
                        reason="ACCOUNT_DISABLED",
                    )
                    write_audit(
                        session,
                        context,
                        action="REFRESH",
                        result=AuditResult.FAILURE,
                        reason="ACCOUNT_DISABLED",
                        target_user_id=user.user_id,
                    )
                    pending_error = AccountDisabled()
                else:
                    roles = roles_for_user(session, user.user_id)
                    outcome = self._new_token_pair(
                        session,
                        user,
                        roles,
                        context,
                        now=now,
                        family_id=current.family_id,
                        parent_session_id=current.session_id,
                    )
                    current.replaced_by_session_id = outcome.session_id
                    current.revoked_at = now
                    current.rotated_at = now
                    current.revoke_reason = "ROTATED"
                    write_audit(
                        session,
                        context,
                        action="REFRESH",
                        result=AuditResult.SUCCESS,
                        target_user_id=user.user_id,
                        metadata={
                            "previousSessionId": current.session_id,
                            "newSessionId": outcome.session_id,
                        },
                    )
        if pending_error is not None:
            AUTH_EVENTS.labels("refresh", pending_error.code).inc()
            raise pending_error
        if outcome is None:
            raise RuntimeError("Refresh completed without an outcome")
        AUTH_EVENTS.labels("refresh", "success").inc()
        AUTH_EVENTS.labels("token_issued", "success").inc()
        return outcome

    def logout(self, raw_refresh_token: str | None, context: RequestContext) -> None:
        with self._sessions() as session, session.begin():
            now = database_now(session)
            current = None
            if raw_refresh_token:
                current = session.scalar(
                    select(RefreshSessionModel)
                    .where(
                        RefreshSessionModel.token_hash
                        == self.tokens.hash_refresh_token(raw_refresh_token)
                    )
                    .with_for_update()
                )
            revoked = 0
            if current is not None:
                revoked = revoke_family(
                    session, current.family_id, now=now, reason="LOGOUT"
                )
            write_audit(
                session,
                context,
                action="LOGOUT",
                result=(AuditResult.SUCCESS if revoked else AuditResult.NO_CHANGE),
                target_user_id=current.user_id if current else None,
                metadata={"revokedSessions": revoked},
            )
        AUTH_EVENTS.labels("logout", "success").inc()

    def authenticate_access_token(self, token: str) -> Principal:
        decoded = self.tokens.decode_access_token(token)
        with self._sessions() as session:
            user = session.get(UserModel, decoded.user_id)
            if user is None:
                raise Unauthenticated()
            if user.status != UserStatus.ACTIVE:
                raise AccountDisabled()
            if user.token_version != decoded.token_version:
                raise TokenRevoked()
            current_roles = roles_for_user(session, user.user_id)
            if current_roles != decoded.roles:
                raise TokenRevoked()
        return decoded

    def current_user(self, principal: Principal) -> UserView:
        with self._sessions() as session:
            user = session.get(UserModel, principal.user_id)
            if user is None:
                raise Unauthenticated()
            return to_user_view(session, user)

    def change_role(
        self,
        *,
        actor: Principal,
        target_user_id: str,
        role_name: str,
        action: RoleAction,
        context: RequestContext,
    ) -> RoleChange:
        pending_error: IdentityError | None = None
        result: RoleChange | None = None
        with self._sessions() as session, session.begin():
            target = session.scalar(
                select(UserModel)
                .where(UserModel.user_id == target_user_id)
                .with_for_update()
            )
            role = session.get(RoleModel, role_name)
            if target is None:
                write_audit(
                    session,
                    context,
                    action="ROLE_CHANGE",
                    result=AuditResult.FAILURE,
                    reason="USER_NOT_FOUND",
                    actor_id=actor.user_id,
                )
                pending_error = UserNotFound()
            elif role is None:
                write_audit(
                    session,
                    context,
                    action="ROLE_CHANGE",
                    result=AuditResult.FAILURE,
                    reason="ROLE_NOT_FOUND",
                    actor_id=actor.user_id,
                    target_user_id=target_user_id,
                )
                pending_error = RoleNotFound()
            elif (
                action == RoleAction.REVOKE
                and role_name == RoleName.ADMIN
                and actor.user_id == target_user_id
            ):
                write_audit(
                    session,
                    context,
                    action="ROLE_CHANGE",
                    result=AuditResult.FAILURE,
                    reason="SELF_ADMIN_REVOKE_FORBIDDEN",
                    actor_id=actor.user_id,
                    target_user_id=target_user_id,
                )
                pending_error = Forbidden(
                    "An administrator cannot revoke own ADMIN role"
                )
            else:
                existing = session.get(
                    UserRoleModel,
                    {"user_id": target_user_id, "role_name": role_name},
                )
                changed = False
                if action == RoleAction.ASSIGN and existing is None:
                    session.add(
                        UserRoleModel(
                            user_id=target_user_id,
                            role_name=role_name,
                            assigned_by=actor.user_id,
                        )
                    )
                    changed = True
                elif action == RoleAction.REVOKE and existing is not None:
                    session.delete(existing)
                    changed = True
                if changed:
                    target.token_version += 1
                    target.updated_at = database_now(session)
                    session.flush()
                write_audit(
                    session,
                    context,
                    action="ROLE_CHANGE",
                    result=(AuditResult.SUCCESS if changed else AuditResult.NO_CHANGE),
                    actor_id=actor.user_id,
                    target_user_id=target_user_id,
                    metadata={"role": role_name, "action": action.value},
                )
                result = RoleChange(
                    user=to_user_view(session, target),
                    role=role_name,
                    action=action,
                    changed=changed,
                )
        if pending_error is not None:
            AUTH_EVENTS.labels("role_change", pending_error.code).inc()
            raise pending_error
        if result is None:
            raise RuntimeError("Role change completed without a result")
        AUTH_EVENTS.labels("role_change", "success").inc()
        return result

    def bootstrap_admin(
        self, email: str, password: str, context: RequestContext
    ) -> UserView:
        try:
            user = self.register(email, password, context)
        except EmailAlreadyExists:
            _, normalized = normalize_email(email)
            with self._sessions() as session:
                existing = session.scalar(
                    select(UserModel).where(UserModel.normalized_email == normalized)
                )
                if existing is None:
                    raise
                user = to_user_view(session, existing)
        with self._sessions() as session, session.begin():
            model = session.scalar(
                select(UserModel)
                .where(UserModel.user_id == user.user_id)
                .with_for_update()
            )
            if model is None:
                raise UserNotFound()
            existing_role = session.get(
                UserRoleModel,
                {"user_id": model.user_id, "role_name": RoleName.ADMIN},
            )
            if existing_role is None:
                session.add(
                    UserRoleModel(
                        user_id=model.user_id,
                        role_name=RoleName.ADMIN,
                        assigned_by=None,
                    )
                )
                model.token_version += 1
                model.updated_at = database_now(session)
            write_audit(
                session,
                context,
                action="BOOTSTRAP_ADMIN",
                result=(
                    AuditResult.SUCCESS
                    if existing_role is None
                    else AuditResult.NO_CHANGE
                ),
                target_user_id=model.user_id,
            )
            session.flush()
            return to_user_view(session, model)
