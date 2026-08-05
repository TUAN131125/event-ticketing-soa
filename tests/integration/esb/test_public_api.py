from __future__ import annotations

from pathlib import Path

import jwt
import pytest
import yaml
from alembic import command
from alembic.config import Config
from app.application.queries import QueryService
from app.config import Settings
from app.dependencies import RuntimeContainer
from app.domain.models import OperationResult, Principal
from app.main import create_app
from app.persistence.memory import InMemoryRepositories
from app.security.jwt import WebSocketTicketIssuer
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fakes import FakeProviders
from fastapi.testclient import TestClient

GATEWAY_ROOT = Path(__file__).resolve().parents[3] / "gateway" / "booking-orchestrator"


class FakeAuth:
    async def verify(self, token: str) -> Principal:
        if token == "invalid":
            from app.domain.errors import AuthenticationFailed

            raise AuthenticationFailed()
        return Principal("identity-subject", ("CUSTOMER", "ADMIN"))


class BookingStub:
    async def execute(self, command, context):
        return OperationResult(
            201,
            {
                "bookingId": "BK-1",
                "status": "CONFIRMED",
                "total": {"amountMinor": 100000, "currency": "VND"},
                "reservationId": "RES-1",
                "paymentId": "PAY-1",
                "ticketIds": ["TKT-1"],
                "correlationId": context.correlation_id,
            },
        )


class CancellationStub:
    async def execute(self, booking_id, idempotency_key, context):
        return OperationResult(
            200,
            {
                "bookingId": booking_id,
                "status": "CANCELLED",
                "total": {"amountMinor": 100000, "currency": "VND"},
                "reservationId": "RES-1",
                "paymentId": "PAY-1",
                "ticketIds": ["TKT-1"],
                "correlationId": context.correlation_id,
            },
        )


def private_key() -> str:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


@pytest.fixture
def api() -> tuple[TestClient, FakeProviders, str]:
    providers = FakeProviders()
    repositories = InMemoryRepositories()
    repositories.traces.append(
        {
            "correlationId": "CORRELATION-0001",
            "service": "booking-service",
            "operation": "getBooking",
            "status": "SUCCESS",
            "durationMs": 2,
            "errorCode": None,
        }
    )
    key = private_key()
    container = RuntimeContainer(
        BookingStub(),
        CancellationStub(),
        QueryService(providers, providers, repositories),
        FakeAuth(),
        WebSocketTicketIssuer(
            key, "booking-orchestrator", "realtime-status-service", "ws-1", 45
        ),
        providers,
    )
    app = create_app(
        Settings(
            environment="test",
            verify_contract_freeze=False,
        ),
        container,
    )
    with TestClient(app) as client:
        yield client, providers, key


def auth(token: str = "valid") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_all_eight_public_routes_execute_with_controlled_test_doubles(api) -> None:
    client, _, _ = api
    correlation = "CORRELATION-0001"
    responses = [
        client.get("/api/events"),
        client.get("/api/events/EVT-1"),
        client.post(
            "/api/bookings",
            headers={
                **auth(),
                "Idempotency-Key": "booking-key-001",
                "X-Correlation-ID": correlation,
            },
            json={
                "customerId": "UNTRUSTED",
                "eventId": "EVT-1",
                "seatIds": ["SEAT-1"],
                "paymentMethodToken": "method-token",
            },
        ),
        client.get("/api/bookings/BK-1", headers=auth()),
        client.post(
            "/api/bookings/BK-1/cancel",
            headers={**auth(), "Idempotency-Key": "cancel-key-001"},
        ),
        client.get("/api/health"),
        client.get(f"/api/traces/{correlation}", headers=auth()),
        client.post(
            "/api/realtime/ws-tickets",
            headers={**auth(), "X-Correlation-ID": correlation},
            json={"bookingId": "BK-1"},
        ),
    ]
    assert [response.status_code for response in responses] == [
        200,
        200,
        201,
        200,
        200,
        200,
        200,
        201,
    ]
    assert responses[2].json()["status"] == "CONFIRMED"
    assert responses[4].json()["status"] == "CANCELLED"


def test_protected_routes_fail_closed_and_errors_use_common_envelope(api) -> None:
    client, _, _ = api
    response = client.get("/api/bookings/BK-1")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    invalid = client.get("/api/bookings/BK-1", headers=auth("invalid"))
    assert invalid.status_code == 401
    assert "token" not in invalid.text.lower()


def test_request_validation_rejects_extra_and_duplicate_seats(api) -> None:
    client, _, _ = api
    headers = {**auth(), "Idempotency-Key": "booking-key-001"}
    payload = {
        "customerId": "UNTRUSTED",
        "eventId": "EVT-1",
        "seatIds": ["SEAT-1", "SEAT-1"],
        "paymentMethodToken": "method-token",
        "extra": True,
    }
    response = client.post("/api/bookings", headers=headers, json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_ws_ticket_is_only_issued_after_access_decision_and_never_uses_query(
    api,
) -> None:
    client, providers, key = api
    response = client.post(
        "/api/realtime/ws-tickets",
        headers={**auth(), "X-Correlation-ID": "CORRELATION-0001"},
        json={"bookingId": "BK-1"},
    )
    assert response.status_code == 201
    assert providers.calls[0][0] == "bookingAccessDecision"
    public = serialization.load_pem_private_key(
        key.encode(), password=None
    ).public_key()
    claims = jwt.decode(
        response.json()["ticket"],
        public,
        algorithms=["RS256"],
        audience="realtime-status-service",
        issuer="booking-orchestrator",
    )
    assert claims["bookingId"] == "BK-1"
    assert claims["scope"] == "booking:status:read"
    assert claims["jti"]
    assert claims["exp"] - claims["iat"] <= 60
    assert b"ticket=" not in response.request.url.query


def test_generated_runtime_openapi_matches_canonical_routes_security_headers_and_statuses(
    api,
) -> None:
    client, _, _ = api
    generated = client.get("/openapi.json").json()
    root = Path(__file__).resolve().parents[3]
    canonical = yaml.safe_load(
        (root / "contracts" / "esb-public-api.yaml").read_text(
            encoding="utf-8"
        )
    )
    expected = {}
    for path, path_item in canonical["paths"].items():
        for method, operation in path_item.items():
            if method in {"get", "post"}:
                expected[(method, path)] = operation
    actual = {
        (method, path): operation
        for path, path_item in generated["paths"].items()
        for method, operation in path_item.items()
        if method in {"get", "post"}
    }
    assert set(actual) == set(expected)
    for key, operation in expected.items():
        runtime = actual[key]
        assert runtime["operationId"] == operation["operationId"]
        assert set(runtime["responses"]) == set(operation["responses"])
        expected_security = operation.get("security", canonical.get("security", []))
        assert runtime.get("security", []) == expected_security
        required_headers = set()
        for parameter in operation.get("parameters", []):
            reference = parameter.get("$ref", "")
            if reference.startswith("#/components/parameters/"):
                component_name = reference.split("/")[-1]
                component = canonical["components"]["parameters"][component_name]
                required_headers.add((component_name, component.get("required", False)))
        runtime_headers = {
            (parameter["name"], parameter.get("required", False))
            for parameter in runtime.get("parameters", [])
            if parameter["in"] == "header"
        }
        translated = {
            ("Idempotency-Key", required)
            if name == "IdempotencyKey"
            else ("X-Correlation-ID", required)
            if name in {"CorrelationId", "RequiredCorrelationId"}
            else ("traceparent", required)
            for name, required in required_headers
        }
        assert translated <= runtime_headers


def test_real_composition_root_starts_with_sql_persistence_and_clean_shutdown(
    tmp_path: Path,
) -> None:
    key = private_key()
    database_url = f"sqlite+aiosqlite:///{tmp_path / 'runtime.db'}"
    migration = Config(str(GATEWAY_ROOT / "alembic.ini"))
    migration.set_main_option("script_location", str(GATEWAY_ROOT / "alembic"))
    migration.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(migration, "head")
    settings = Settings(
        environment="test",
        database_url=database_url,
        verify_contract_freeze=True,
        internal_service_private_key=key,
        ws_ticket_private_key=key,
        notification_webhook_secret="n" * 32,
        identity_jwks_url="http://identity.test/jwks",
        customer_service_url="http://customer.test",
        event_service_url="http://event.test",
        seat_service_url="http://seat.test/soap",
        seat_service_token="seat-test-token",
        booking_service_url="http://booking.test",
        payment_service_url="http://payment.test",
        ticket_service_url="http://ticket.test",
        notification_service_url="http://notification.test",
        realtime_service_url="http://realtime.test",
        realtime_internal_service_token="realtime-test-token",
        outbox_poll_seconds=0.01,
        reconciliation_poll_seconds=0.01,
    )
    app = create_app(settings)
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "UP"}
