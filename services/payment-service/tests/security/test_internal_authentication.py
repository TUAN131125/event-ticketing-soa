from fastapi.testclient import TestClient

from app.main import create_app
from tests.factories import TEST_SERVICE_TOKEN
from tests.factories import build_settings as settings


def test_payment_data_requires_internal_service_token() -> None:
    with TestClient(create_app(settings())) as client:
        missing = client.get("/payments/PAY00000001")
        wrong = client.get(
            "/payments/PAY00000001", headers={"X-Service-Token": "wrong"}
        )
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert missing.json()["error"]["code"] == "AUTHENTICATION_FAILED"
    assert "X-Correlation-ID" in missing.headers


def test_liveness_is_public_and_does_not_touch_database() -> None:
    with TestClient(create_app(settings())) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "UP"


def test_authenticated_request_requires_auditable_caller_name() -> None:
    with TestClient(create_app(settings())) as client:
        response = client.get(
            "/payments/PAY00000001",
            headers={"X-Service-Token": TEST_SERVICE_TOKEN},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
