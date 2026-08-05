from app.infrastructure.database.models import Base


def test_identity_metadata_contains_all_owned_tables():
    assert set(Base.metadata.tables) == {
        "identity.users",
        "identity.roles",
        "identity.user_roles",
        "identity.refresh_sessions",
        "identity.auth_audit",
        "identity.auth_rate_limits",
    }
