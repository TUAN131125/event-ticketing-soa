"""Pure authorization and session policies."""

from __future__ import annotations

from datetime import datetime

from app.domain.enums import RoleAction, RoleName, SessionRevokeReason


def is_refresh_token_reuse(
    *,
    replaced_by_session_id: str | None,
    revoked_at: datetime | None,
    revoke_reason: str | None,
) -> bool:
    return replaced_by_session_id is not None or (
        revoked_at is not None
        and revoke_reason
        in {
            SessionRevokeReason.ROTATED.value,
            SessionRevokeReason.REUSE_DETECTED.value,
        }
    )


def is_self_admin_revoke(
    *,
    actor_user_id: str,
    target_user_id: str,
    role_name: str,
    action: RoleAction,
) -> bool:
    return (
        action == RoleAction.REVOKE
        and role_name == RoleName.ADMIN.value
        and actor_user_id == target_user_id
    )
