import pytest

from app.config import Settings


def test_missing_service_jwt_configuration_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("TICKET_DATABASE_URL", "sqlite:///ticket-test.db")
    monkeypatch.setenv("TICKET_QR_SIGNING_KEY", "test-signing-key")
    monkeypatch.delenv("TICKET_SERVICE_JWT_ISSUER", raising=False)
    with pytest.raises(ValueError, match="TICKET_SERVICE_JWT_ISSUER"):
        Settings.from_environment()
