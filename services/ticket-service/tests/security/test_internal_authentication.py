from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def settings() -> Settings:
    return Settings(
        app_name="ticket-service",
        app_env="test",
        database_url="postgresql+psycopg://ticket:ticket@localhost:5439/ticket",
        service_token="test-service-token",
        qr_signing_key="test-qr-signing-key-that-is-long-enough",
        db_pool_size=1,
        db_max_overflow=0,
        db_pool_timeout_seconds=1,
        db_connect_timeout_seconds=1,
        db_lock_timeout_ms=1_000,
        db_statement_timeout_ms=5_000,
        idempotency_ttl_seconds=3_600,
        log_level="WARNING",
        docs_enabled=True,
    )


def test_ticket_data_requires_internal_service_token() -> None:
    with TestClient(create_app(settings())) as client:
        missing = client.get("/tickets/TKT000000001")
        wrong = client.get(
            "/tickets/TKT000000001", headers={"X-Service-Token": "wrong"}
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
            "/tickets/TKT000000001",
            headers={"X-Service-Token": "test-service-token"},
        )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_check_in_requires_staff_actor_before_database_access() -> None:
    headers = {
        "X-Service-Token": "test-service-token",
        "X-Caller-Service": "checkin-gateway",
        "X-Actor-ID": "USER-1",
        "Idempotency-Key": "CHECKIN-1",
    }
    body = {"qrToken": "token", "gateId": "GATE-A", "expectedVersion": 1}
    with TestClient(create_app(settings())) as client:
        no_role = client.post(
            "/tickets/TKT000000001/check-in", headers=headers, json=body
        )
        wrong_role = client.post(
            "/tickets/TKT000000001/check-in",
            headers={**headers, "X-Actor-Roles": "CUSTOMER"},
            json=body,
        )
    assert no_role.status_code == 403
    assert wrong_role.status_code == 403
    assert no_role.json()["error"]["code"] == "FORBIDDEN"
