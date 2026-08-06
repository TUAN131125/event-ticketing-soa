import pytest

from app.config import DEVELOPMENT_TOKEN, Settings


def test_production_rejects_default_service_token(monkeypatch) -> None:
    monkeypatch.setenv("PAYMENT_APP_ENV", "production")
    monkeypatch.setenv("PAYMENT_SERVICE_TOKEN", DEVELOPMENT_TOKEN)
    with pytest.raises(ValueError, match="PAYMENT_SERVICE_TOKEN"):
        Settings.from_environment()


def test_non_local_environments_require_an_explicit_token(monkeypatch) -> None:
    monkeypatch.setenv("PAYMENT_APP_ENV", "staging")
    monkeypatch.delenv("PAYMENT_SERVICE_TOKEN", raising=False)
    with pytest.raises(ValueError, match="PAYMENT_SERVICE_TOKEN"):
        Settings.from_environment()


def test_non_local_environments_reject_a_short_token(monkeypatch) -> None:
    monkeypatch.setenv("PAYMENT_APP_ENV", "staging")
    monkeypatch.setenv("PAYMENT_SERVICE_TOKEN", "too-short")
    with pytest.raises(ValueError, match="32 characters"):
        Settings.from_environment()


def test_local_settings_have_bounded_defaults(monkeypatch) -> None:
    monkeypatch.setenv("PAYMENT_APP_ENV", "local")
    monkeypatch.delenv("PAYMENT_SERVICE_TOKEN", raising=False)
    settings = Settings.from_environment()
    assert settings.db_connect_timeout_seconds <= settings.db_pool_timeout_seconds
    assert settings.db_lock_timeout_ms < settings.db_statement_timeout_ms
    assert settings.docs_enabled is True
    assert settings.outbox_webhook_enabled is False


def test_non_local_environments_require_provider_callback_secret(monkeypatch) -> None:
    monkeypatch.setenv("PAYMENT_APP_ENV", "staging")
    monkeypatch.setenv("PAYMENT_SERVICE_TOKEN", "s" * 32)
    monkeypatch.delenv("PAYMENT_PROVIDER_CALLBACK_SECRET", raising=False)
    with pytest.raises(ValueError, match="PAYMENT_PROVIDER_CALLBACK_SECRET"):
        Settings.from_environment()


def test_non_local_environments_reject_weak_provider_callback_secret(
    monkeypatch,
) -> None:
    monkeypatch.setenv("PAYMENT_APP_ENV", "staging")
    monkeypatch.setenv("PAYMENT_SERVICE_TOKEN", "s" * 32)
    monkeypatch.setenv("PAYMENT_PROVIDER_CALLBACK_SECRET", "too-short")
    with pytest.raises(ValueError, match="32 characters"):
        Settings.from_environment()
