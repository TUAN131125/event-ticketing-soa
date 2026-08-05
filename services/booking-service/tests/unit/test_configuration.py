import pytest

from app.config import Settings


def test_production_rejects_default_service_token(monkeypatch) -> None:
    monkeypatch.setenv("BOOKING_APP_ENV", "production")
    monkeypatch.setenv("BOOKING_DATABASE_URL", "sqlite:///booking-test.db")
    monkeypatch.setenv("BOOKING_SERVICE_TOKEN", "local-development-token")
    with pytest.raises(ValueError, match="BOOKING_SERVICE_TOKEN"):
        Settings.from_environment()


def test_local_settings_have_bounded_defaults(monkeypatch) -> None:
    monkeypatch.setenv("BOOKING_APP_ENV", "local")
    monkeypatch.setenv("BOOKING_DATABASE_URL", "sqlite:///booking-test.db")
    monkeypatch.setenv("BOOKING_SERVICE_TOKEN", "test-service-token")
    settings = Settings.from_environment()
    assert settings.db_connect_timeout_seconds <= settings.db_pool_timeout_seconds
    assert settings.db_lock_timeout_ms < settings.db_statement_timeout_ms
    assert settings.docs_enabled is True
