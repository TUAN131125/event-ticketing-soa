"""Refresh-token rotation and logout use cases."""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from app.application.metrics import record_failure, record_success
from app.application.outcomes import LoginOutcome
from app.application.session_issuer import TokenSessionIssuer
from app.domain.enums import (
    AuditAction,
    AuditReason,
    AuditResult,
    SessionRevokeReason,
    UserStatus,
)
from app.domain.exceptions import (
    AccountDisabled,
    IdentityError,
    InvalidRefreshToken,
    RefreshTokenReuseDetected,
)
from app.domain.policies import is_refresh_token_reuse
from app.domain.value_objects import RequestContext
from app.infrastructure.database.repositories import (
    AuditRepository,
    RefreshSessionRepository,
    UserRepository,
    database_now,
)
from app.security.tokens import TokenService


class SessionManagementUseCase:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        token_service: TokenService,
        session_issuer: TokenSessionIssuer,
    ) -> None:
        self._sessions = session_factory
        self._tokens = token_service
        self._session_issuer = session_issuer

    def refresh(
        self, raw_refresh_token: str, context: RequestContext
    ) -> LoginOutcome:
        token_hash = self._tokens.hash_refresh_token(raw_refresh_token)
        pending_error: IdentityError | None = None
        outcome: LoginOutcome | None = None

        with self._sessions() as session, session.begin():
            refresh_sessions = RefreshSessionRepository(session)
            users = UserRepository(session)
            audit = AuditRepository(session)
            current = refresh_sessions.find_by_token_hash(
                token_hash, for_update=True
            )
            now = database_now(session)

            if current is None:
                audit.record(
                    context,
                    action=AuditAction.REFRESH,
                    result=AuditResult.FAILURE,
                    reason=AuditReason.INVALID_REFRESH_TOKEN,
                )
                pending_error = InvalidRefreshToken()
            elif is_refresh_token_reuse(
                replaced_by_session_id=current.replaced_by_session_id,
                revoked_at=current.revoked_at,
                revoke_reason=current.revoke_reason,
            ):
                refresh_sessions.revoke_family(
                    current.family_id,
                    now=now,
                    reason=SessionRevokeReason.REUSE_DETECTED,
                )
                audit.record(
                    context,
                    action=AuditAction.REFRESH,
                    result=AuditResult.FAILURE,
                    reason=AuditReason.REFRESH_TOKEN_REUSE_DETECTED,
                    target_user_id=current.user_id,
                    metadata={"familyId": current.family_id},
                )
                pending_error = RefreshTokenReuseDetected()
            elif current.revoked_at is not None or current.expires_at <= now:
                if current.revoked_at is None:
                    current.revoked_at = now
                    current.revoke_reason = SessionRevokeReason.EXPIRED.value
                audit.record(
                    context,
                    action=AuditAction.REFRESH,
                    result=AuditResult.FAILURE,
                    reason=AuditReason.INVALID_REFRESH_TOKEN,
                    target_user_id=current.user_id,
                )
                pending_error = InvalidRefreshToken()
            else:
                user = users.find_by_id(current.user_id, for_update=True)
                if user is None:
                    audit.record(
                        context,
                        action=AuditAction.REFRESH,
                        result=AuditResult.FAILURE,
                        reason=AuditReason.INVALID_REFRESH_TOKEN,
                        target_user_id=current.user_id,
                    )
                    pending_error = InvalidRefreshToken()
                elif user.status != UserStatus.ACTIVE:
                    refresh_sessions.revoke_family(
                        current.family_id,
                        now=now,
                        reason=SessionRevokeReason.ACCOUNT_DISABLED,
                    )
                    audit.record(
                        context,
                        action=AuditAction.REFRESH,
                        result=AuditResult.FAILURE,
                        reason=AuditReason.ACCOUNT_DISABLED,
                        target_user_id=user.user_id,
                    )
                    pending_error = AccountDisabled()
                else:
                    outcome = self._session_issuer.issue(
                        session,
                        user,
                        users.roles_for(user.user_id),
                        context,
                        now=now,
                        family_id=current.family_id,
                        parent_session_id=current.session_id,
                    )
                    current.replaced_by_session_id = outcome.session_id
                    current.revoked_at = now
                    current.rotated_at = now
                    current.revoke_reason = SessionRevokeReason.ROTATED.value
                    audit.record(
                        context,
                        action=AuditAction.REFRESH,
                        result=AuditResult.SUCCESS,
                        target_user_id=user.user_id,
                        metadata={
                            "previousSessionId": current.session_id,
                            "newSessionId": outcome.session_id,
                        },
                    )

        if pending_error is not None:
            record_failure("refresh", pending_error)
            raise pending_error
        if outcome is None:
            raise RuntimeError("Refresh completed without an outcome")
        record_success("refresh")
        record_success("token_issued")
        return outcome

    def logout(self, raw_refresh_token: str | None, context: RequestContext) -> None:
        with self._sessions() as session, session.begin():
            refresh_sessions = RefreshSessionRepository(session)
            now = database_now(session)
            current = None
            if raw_refresh_token:
                current = refresh_sessions.find_by_token_hash(
                    self._tokens.hash_refresh_token(raw_refresh_token),
                    for_update=True,
                )
            revoked = 0
            if current is not None:
                revoked = refresh_sessions.revoke_family(
                    current.family_id,
                    now=now,
                    reason=SessionRevokeReason.LOGOUT,
                )
            AuditRepository(session).record(
                context,
                action=AuditAction.LOGOUT,
                result=AuditResult.SUCCESS if revoked else AuditResult.NO_CHANGE,
                target_user_id=current.user_id if current is not None else None,
                metadata={"revokedSessions": revoked},
            )
        record_success("logout")
