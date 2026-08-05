import pytest

from app.config import Settings


def test_missing_service_jwt_configuration_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("PAYMENT_DATABASE_URL", "sqlite:///payment-test.db")
    monkeypatch.setenv("PAYMENT_PROVIDER_HMAC_SECRET", "test-hmac")
    monkeypatch.delenv("PAYMENT_SERVICE_JWT_ISSUER", raising=False)
    with pytest.raises(ValueError, match="PAYMENT_SERVICE_JWT_ISSUER"):
        Settings.from_environment()
