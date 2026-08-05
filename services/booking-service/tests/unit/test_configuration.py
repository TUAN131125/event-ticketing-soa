import pytest

from app.config import Settings


def test_missing_service_jwt_configuration_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("BOOKING_DATABASE_URL", "sqlite:///booking-test.db")
    monkeypatch.delenv("BOOKING_SERVICE_JWT_ISSUER", raising=False)
    with pytest.raises(ValueError, match="BOOKING_SERVICE_JWT_ISSUER"):
        Settings.from_environment()
