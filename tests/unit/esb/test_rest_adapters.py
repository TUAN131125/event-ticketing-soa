from __future__ import annotations

import hashlib
import hmac
import json
from urllib.parse import urlsplit

import httpx
import jwt
import pytest
from app.adapters.rest.base import RestClient
from app.adapters.rest.providers import (
    BookingRestAdapter,
    CustomerRestAdapter,
    EventRestAdapter,
    NotificationRestAdapter,
    PaymentRestAdapter,
    RealtimeRestAdapter,
    TicketRestAdapter,
)
from app.domain.models import Money
from app.resilience.policies import (
    Bulkhead,
    CircuitBreaker,
    ResilienceExecutor,
    RetryClass,
)
from app.security.jwt import JwtSigner
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fakes import request_context


def executor() -> ResilienceExecutor:
    return ResilienceExecutor(
        {
            RetryClass.NONE: 1,
            RetryClass.SAFE_READ: 1,
            RetryClass.IDEMPOTENT_COMMAND: 1,
            RetryClass.RECONCILIATION_ONLY: 1,
            RetryClass.SIDE_EFFECT: 1,
        },
        0,
        CircuitBreaker(20, 1),
        Bulkhead(5),
    )


def signer() -> tuple[JwtSigner, object]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    return JwtSigner(
        private, "booking-orchestrator", "booking-orchestrator", "internal-1"
    ), key.public_key()


@pytest.mark.asyncio
async def test_rest_provider_adapters_use_canonical_paths_and_audience_bound_service_jwt() -> (
    None
):
    calls: list[tuple[str, str, str]] = []
    token_signer, public_key = signer()

    async def handler(request: httpx.Request) -> httpx.Response:
        audience = request.url.host or ""
        token = request.headers["Authorization"].split(" ", 1)[1]
        claims = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=audience,
            issuer="booking-orchestrator",
        )
        assert claims["sub"] == "booking-orchestrator"
        assert claims["jti"]
        if request.url.path.endswith("/access-decisions"):
            assert "Idempotency-Key" not in request.headers
            assert "If-Match" not in request.headers
            assert request.headers["X-Correlation-ID"]
        calls.append((request.method, request.url.path, audience))
        if request.url.path in {"/events", "/tickets:issue", "/bookings/BK-1/tickets"}:
            return httpx.Response(200, json=[])
        return httpx.Response(200, json={"status": "OK"})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def client(audience: str) -> RestClient:
        return RestClient(
            f"https://{audience}", audience, http, token_signer, executor()
        )

    context = request_context()
    customer = CustomerRestAdapter(client("customer-service"))
    events = EventRestAdapter(client("event-service"))
    bookings = BookingRestAdapter(client("booking-service"))
    payments = PaymentRestAdapter(client("payment-service"))
    tickets = TicketRestAdapter(client("ticket-service"))

    await customer.resolve_mapping("identity-subject", context)
    await customer.get_customer("CUS-1", context)
    await events.list_events(context)
    await events.get_event("EVT-1", context)
    await events.get_sale_eligibility("EVT-1", context)
    await bookings.create_booking({}, "booking-key", context)
    await bookings.get_booking("BK-1", context)
    await bookings.decide_access("BK-1", context)
    await bookings.transition("bookingConfirm", "BK-1", {}, "confirm-key", context)
    await payments.create_payment(
        "BK-1", Money(100000, "VND"), "method-token", "payment-key", context
    )
    await payments.get_payment("PAY-1", context)
    await payments.command("reconcilePayment", "PAY-1", {}, "reconcile-key", context)
    await tickets.issue_tickets({}, "ticket-key", context)
    await tickets.list_booking_tickets("BK-1", context)
    await tickets.cancel_ticket("TKT-1", "cancel-ticket-key", context)

    assert {(method, path) for method, path, _ in calls} == {
        ("GET", "/internal/identity-mappings/identity-subject"),
        ("GET", "/customers/CUS-1"),
        ("GET", "/events"),
        ("GET", "/events/EVT-1"),
        ("GET", "/events/EVT-1/sale-eligibility"),
        ("POST", "/bookings"),
        ("GET", "/bookings/BK-1"),
        ("POST", "/internal/bookings/BK-1/access-decisions"),
        ("POST", "/bookings/BK-1/confirm"),
        ("POST", "/payments"),
        ("GET", "/payments/PAY-1"),
        ("POST", "/payments/PAY-1/reconcile"),
        ("POST", "/tickets:issue"),
        ("GET", "/bookings/BK-1/tickets"),
        ("GET", "/tickets/TKT-1"),
        ("POST", "/tickets/TKT-1/cancel"),
    }
    await http.aclose()


@pytest.mark.asyncio
async def test_side_effect_adapters_send_signed_raw_notification_and_internal_realtime_event() -> (
    None
):
    token_signer, _ = signer()
    secret = "notification-secret-that-is-at-least-32-bytes"
    seen: dict[str, httpx.Request] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen[urlsplit(str(request.url)).path] = request
        return httpx.Response(202, json={"accepted": True})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    notification = NotificationRestAdapter(
        RestClient(
            "https://notification-service",
            "notification-service",
            http,
            token_signer,
            executor(),
        ),
        secret,
    )
    realtime = RealtimeRestAdapter(
        RestClient(
            "https://realtime-status-service",
            "realtime-status-service",
            http,
            token_signer,
            executor(),
        )
    )
    context = request_context()
    payload = {"bookingId": "BK-1", "status": "CONFIRMED", "sequence": 3}
    await notification.publish(payload, "MSG-NOTIFY-1", context)
    await realtime.publish(payload, "MSG-REALTIME-1", context)

    notification_request = seen["/webhooks/events"]
    timestamp = notification_request.headers["X-Webhook-Timestamp"]
    expected = hmac.new(
        secret.encode(),
        timestamp.encode() + b"." + notification_request.content,
        hashlib.sha256,
    ).hexdigest()
    assert hmac.compare_digest(
        notification_request.headers["X-Webhook-Signature"], f"sha256={expected}"
    )
    assert json.loads(notification_request.content)["eventId"] == "MSG-NOTIFY-1"
    realtime_body = json.loads(seen["/internal/status-events"].content)
    assert (
        seen["/internal/status-events"].headers["Authorization"].startswith("Bearer ")
    )
    assert (
        seen["/internal/status-events"].headers["X-Correlation-ID"]
        == context.correlation_id
    )
    assert realtime_body["messageId"] == "MSG-REALTIME-1"
    assert realtime_body["sequence"] == 3
    await http.aclose()
