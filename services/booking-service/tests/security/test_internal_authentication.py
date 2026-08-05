from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_booking_data_requires_valid_service_jwt(booking_settings: Settings) -> None:
    with TestClient(create_app(booking_settings)) as client:
        missing = client.get("/bookings/BK00000001")
        malformed = client.get(
            "/bookings/BK00000001", headers={"Authorization": "Bearer invalid"}
        )
    assert missing.status_code == 401
    assert malformed.status_code == 401
    assert missing.json()["error"]["code"] == "AUTHENTICATION_FAILED"


def test_liveness_is_public(booking_settings: Settings) -> None:
    with TestClient(create_app(booking_settings)) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "UP"


def test_wrong_service_audience_is_rejected(booking_settings: Settings) -> None:
    token = booking_settings.service_jwt_signing.signer().issue("payment-service")
    with TestClient(create_app(booking_settings)) as client:
        response = client.get(
            "/bookings/BK00000001", headers={"Authorization": f"Bearer {token}"}
        )
    assert response.status_code == 401
