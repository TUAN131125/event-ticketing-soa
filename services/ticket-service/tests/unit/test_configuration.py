import pytest

from app.config import Settings


def test_production_requires_service_and_qr_secrets(monkeypatch) -> None:
    monkeypatch.setenv("TICKET_APP_ENV", "production")
    monkeypatch.setenv("TICKET_SERVICE_TOKEN", "short")
    monkeypatch.setenv("TICKET_QR_SIGNING_KEY", "short")
    with pytest.raises(ValueError, match="TICKET_SERVICE_TOKEN"):
        Settings.from_environment()

    monkeypatch.setenv("TICKET_SERVICE_TOKEN", "S" * 32)
    with pytest.raises(ValueError, match="TICKET_QR_SIGNING_KEY"):
        Settings.from_environment()


def test_local_settings_have_bounded_defaults(monkeypatch) -> None:
    monkeypatch.setenv("TICKET_APP_ENV", "local")
    monkeypatch.delenv("TICKET_SERVICE_TOKEN", raising=False)
    monkeypatch.delenv("TICKET_QR_SIGNING_KEY", raising=False)
    settings = Settings.from_environment()
    assert settings.db_connect_timeout_seconds <= settings.db_pool_timeout_seconds
    assert settings.db_lock_timeout_ms < settings.db_statement_timeout_ms
    assert settings.docs_enabled is True
