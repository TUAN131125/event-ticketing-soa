from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import sessionmaker

from app.application.service import IdentityService
from app.domain.enums import RoleAction, RoleName, SessionRevokeReason
from app.domain.policies import is_refresh_token_reuse, is_self_admin_revoke
from app.security.passwords import PasswordService
from app.security.tokens import TokenService


def test_identity_service_facade_exposes_stable_jwks(unit_settings):
    service = IdentityService(
        unit_settings,
        sessionmaker(),
        PasswordService(unit_settings),
        TokenService(unit_settings),
    )

    assert service.tokens is not None
    assert service.jwks()["keys"][0]["kid"] == unit_settings.key_id


def test_refresh_reuse_policy():
    assert is_refresh_token_reuse(
        replaced_by_session_id="session-2",
        revoked_at=None,
        revoke_reason=None,
    )
    assert not is_refresh_token_reuse(
        replaced_by_session_id=None,
        revoked_at=None,
        revoke_reason=None,
    )
    assert is_refresh_token_reuse(
        replaced_by_session_id=None,
        revoked_at=datetime.now(UTC),
        revoke_reason=SessionRevokeReason.ROTATED.value,
    )


def test_self_admin_revoke_policy():
    assert is_self_admin_revoke(
        actor_user_id="user-1",
        target_user_id="user-1",
        role_name=RoleName.ADMIN.value,
        action=RoleAction.REVOKE,
    )
    assert not is_self_admin_revoke(
        actor_user_id="user-1",
        target_user_id="user-2",
        role_name=RoleName.ADMIN.value,
        action=RoleAction.REVOKE,
    )
