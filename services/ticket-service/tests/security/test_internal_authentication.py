from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_ticket_data_requires_service_jwt(ticket_settings: Settings) -> None:
    with TestClient(create_app(ticket_settings)) as client:
        missing = client.get("/tickets/TKT000000001")
        wrong = client.get(
            "/tickets/TKT000000001", headers={"Authorization": "Bearer wrong"}
        )
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert missing.json()["error"]["code"] == "AUTHENTICATION_FAILED"
    assert "X-Correlation-ID" in missing.headers


def test_liveness_is_public_and_does_not_touch_database(
    ticket_settings: Settings,
) -> None:
    with TestClient(create_app(ticket_settings)) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "UP"
