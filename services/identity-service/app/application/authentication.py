"""Credential login and access-token authentication use cases."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.application.metrics import record_failure, record_success
from app.application.outcomes import LoginOutcome
from app.application.session_issuer import TokenSessionIssuer
from app.config import Settings
from app.domain.entities import UserView
from app.domain.enums import AuditAction, AuditReason, AuditResult, UserStatus
from app.domain.exceptions import (
    AccountDisabled,
    AccountLocked,
    IdentityError,
    InvalidCredentials,
    RateLimited,
    TokenRevoked,
    Unauthenticated,
)
from app.domain.rules import normalize_email
from app.domain.value_objects import Principal, RequestContext
from app.infrastructure.database.repositories import (
    AuditRepository,
    LoginRateLimitRepository,
    UserRepository,
    database_now,
)
from app.security.passwords import PasswordService
from app.security.tokens import TokenService


class AuthenticationUseCase:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        password_service: PasswordService,
        token_service: TokenService,
        session_issuer: TokenSessionIssuer,
    ) -> None:
        self._settings = settings
        self._sessions = session_factory
        self._passwords = password_service
        self._tokens = token_service
        self._session_issuer = session_issuer

    def login(
        self, email: str, password: str, context: RequestContext
    ) -> LoginOutcome:
        _, normalized_email = normalize_email(email)
        pending_error: IdentityError | None = None
        outcome: LoginOutcome | None = None

        with self._sessions() as session, session.begin():
            users = UserRepository(session)
            audit = AuditRepository(session)
            limiter = LoginRateLimitRepository(session)
            retry_after = limiter.consume(
                subject=normalized_email,
                client_ip=context.client_ip,
                window_seconds=self._settings.login_window_seconds,
                limit=self._settings.login_rate_limit,
            )
            if retry_after is not None:
                self._passwords.verify(self._passwords.dummy_hash, password)
                audit.record(
                    context,
                    action=AuditAction.LOGIN,
                    result=AuditResult.FAILURE,
                    reason=AuditReason.RATE_LIMITED,
                )
                pending_error = RateLimited(retry_after)
            else:
                user = users.find_by_normalized_email(
                    normalized_email, for_update=True
                )
                encoded_hash = (
                    user.password_hash
                    if user is not None
                    else self._passwords.dummy_hash
                )
                password_valid = self._passwords.verify(encoded_hash, password)
                now = database_now(session)

                if user is not None and user.locked_until is not None:
                    if user.locked_until > now:
                        retry = int((user.locked_until - now).total_seconds())
                        audit.record(
                            context,
                            action=AuditAction.LOGIN,
                            result=AuditResult.FAILURE,
                            reason=AuditReason.ACCOUNT_LOCKED,
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
                        if user.failed_login_count >= self._settings.lockout_threshold:
                            user.locked_until = now + timedelta(
                                seconds=self._settings.lockout_seconds
                            )
                    audit.record(
                        context,
                        action=AuditAction.LOGIN,
                        result=AuditResult.FAILURE,
                        reason=AuditReason.INVALID_CREDENTIALS,
                        target_user_id=user.user_id if user is not None else None,
                    )
                    pending_error = InvalidCredentials()

                if (
                    pending_error is None
                    and user is not None
                    and user.status != UserStatus.ACTIVE
                ):
                    audit.record(
                        context,
                        action=AuditAction.LOGIN,
                        result=AuditResult.FAILURE,
                        reason=AuditReason.ACCOUNT_DISABLED,
                        target_user_id=user.user_id,
                    )
                    pending_error = AccountDisabled()

                if pending_error is None and user is not None:
                    if self._passwords.needs_rehash(user.password_hash):
                        user.password_hash = self._passwords.hash(password)
                    user.failed_login_count = 0
                    user.locked_until = None
                    user.last_login_at = now
                    user.updated_at = now
                    limiter.reset(
                        subject=normalized_email,
                        client_ip=context.client_ip,
                    )
                    outcome = self._session_issuer.issue(
                        session,
                        user,
                        users.roles_for(user.user_id),
                        context,
                        now=now,
                        family_id=str(uuid.uuid4()),
                        parent_session_id=None,
                    )
                    audit.record(
                        context,
                        action=AuditAction.LOGIN,
                        result=AuditResult.SUCCESS,
                        target_user_id=user.user_id,
                        metadata={"sessionId": outcome.session_id},
                    )

        if pending_error is not None:
            record_failure("login", pending_error)
            raise pending_error
        if outcome is None:
            raise RuntimeError("Login completed without an outcome")
        record_success("login")
        record_success("token_issued")
        return outcome

    def authenticate_access_token(self, token: str) -> Principal:
        principal = self._tokens.decode_access_token(token)
        with self._sessions() as session:
            users = UserRepository(session)
            user = users.find_by_id(principal.user_id)
            if user is None:
                raise Unauthenticated()
            if user.status != UserStatus.ACTIVE:
                raise AccountDisabled()
            if user.token_version != principal.token_version:
                raise TokenRevoked()
            if users.roles_for(user.user_id) != principal.roles:
                raise TokenRevoked()
        return principal

    def current_user(self, principal: Principal) -> UserView:
        with self._sessions() as session:
            users = UserRepository(session)
            user = users.find_by_id(principal.user_id)
            if user is None:
                raise Unauthenticated()
            return users.view(user)
