from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.errors import Unauthenticated
from app.main import create_app
from app.security.ticket_replay import InMemoryTicketReplayStore
from app.security.token_validation import AuthenticatedPrincipal
from app.security.ws_ticket import SignedWebSocketTicketValidator
from app.websocket.endpoint import (
    CLOSE_AUTHENTICATION_TIMEOUT,
    CLOSE_FORBIDDEN,
    CLOSE_UNAUTHENTICATED,
)


class FakeTokenValidator:
    async def validate(self, token: str) -> AuthenticatedPrincipal:
        if token == "owner-token":
            return AuthenticatedPrincipal("C001", frozenset({"CUSTOMER"}), "native-jti")
        raise Unauthenticated()


class FakeAccessChecker:
    async def can_subscribe(
        self, principal: AuthenticatedPrincipal, booking_id: str, correlation_id: str
    ) -> bool:
        del correlation_id
        return principal.subject == "C001" and booking_id == "BK-1"


def ws_headers() -> dict[str, str]:
    return {"Origin": "http://localhost:3000", "X-Correlation-ID": "corr-ws"}


def internal_headers() -> dict[str, str]:
    return {
        "X-Service-Token": "test-internal-token",
        "X-Caller-Service": "booking-service",
        "X-Correlation-ID": "corr-http",
        "Content-Type": "application/json",
    }


def event() -> dict[str, object]:
    return {
        "messageId": "pre-auth-event",
        "bookingId": "BK-1",
        "status": "PENDING",
        "sequence": 1,
        "occurredAt": "2026-08-03T03:00:00Z",
        "correlationId": "corr-event",
        "message": "Booking is being processed",
    }


@pytest.fixture
def ticket_keys(tmp_path: Path) -> tuple[Any, Path]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_path = tmp_path / "ws-ticket-public.pem"
    public_path.write_bytes(
        private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    return private, public_path


def _ticket(private: Any, **overrides: Any) -> str:
    now = int(time.time())
    claims: dict[str, Any] = {
        "iss": "booking-orchestrator",
        "aud": "realtime-status-service",
        "sub": "C001",
        "bookingId": "BK-1",
        "scope": "booking:status:read",
        "iat": now,
        "exp": now + 30,
        "jti": "ticket-jti-1",
    }
    claims.update(overrides)
    return jwt.encode(claims, private, algorithm="RS256", headers={"kid": "esb-1"})


@pytest.fixture
def ticket_client(settings: Any, ticket_keys: tuple[Any, Path]) -> tuple[TestClient, Any]:
    private, public_path = ticket_keys
    validator = SignedWebSocketTicketValidator(
        public_key_path=public_path,
        issuer="booking-orchestrator",
        audience="realtime-status-service",
        key_id="esb-1",
        max_ttl_seconds=60,
    )
    app = create_app(
        settings,
        token_validator=FakeTokenValidator(),
        access_checker=FakeAccessChecker(),
        ws_ticket_validator=validator,
        ticket_replay_store=InMemoryTicketReplayStore(100),
    )
    with TestClient(app) as client:
        yield client, private


def test_valid_ticket_connects_and_does_not_receive_pre_auth_status(
    ticket_client: tuple[TestClient, Any],
) -> None:
    client, private = ticket_client
    with client.websocket_connect("/ws/bookings/BK-1", headers=ws_headers()) as websocket:
        response = client.post("/internal/status-events", headers=internal_headers(), json=event())
        assert response.status_code == 202
        assert response.json()["outcome"] == "no_subscribers"
        websocket.send_json({"type": "authenticate", "ticket": _ticket(private)})
        assert websocket.receive_json()["type"] == "connected"


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"exp": int(time.time()) - 1, "iat": int(time.time()) - 30}, CLOSE_UNAUTHENTICATED),
        ({"iss": "wrong"}, CLOSE_UNAUTHENTICATED),
        ({"aud": "wrong"}, CLOSE_UNAUTHENTICATED),
        ({"scope": "wrong"}, CLOSE_UNAUTHENTICATED),
        ({"bookingId": "BK-2"}, CLOSE_UNAUTHENTICATED),
        (
            {"iat": int(time.time()), "exp": int(time.time()) + 61},
            CLOSE_UNAUTHENTICATED,
        ),
    ],
)
def test_invalid_ticket_claims_are_rejected(
    ticket_client: tuple[TestClient, Any], overrides: dict[str, Any], code: int
) -> None:
    client, private = ticket_client
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect("/ws/bookings/BK-1", headers=ws_headers()) as websocket:
            websocket.send_json({"type": "authenticate", "ticket": _ticket(private, **overrides)})
            websocket.receive_json()
    assert closed.value.code == code


def test_ticket_jti_is_single_use(ticket_client: tuple[TestClient, Any]) -> None:
    client, private = ticket_client
    signed = _ticket(private)
    with client.websocket_connect("/ws/bookings/BK-1", headers=ws_headers()) as first:
        first.send_json({"type": "authenticate", "ticket": signed})
        assert first.receive_json()["type"] == "connected"
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect("/ws/bookings/BK-1", headers=ws_headers()) as second:
            second.send_json({"type": "authenticate", "ticket": signed})
            second.receive_json()
    assert closed.value.code == CLOSE_FORBIDDEN


@pytest.mark.asyncio
async def test_in_memory_replay_store_is_bounded_and_fails_closed() -> None:
    store = InMemoryTicketReplayStore(2, clock=lambda: 100.0)
    assert await store.consume("one", 200) is True
    assert await store.consume("two", 200) is True
    assert await store.consume("three", 200) is False
    assert await store.consume("one", 200) is False


def test_ticket_authentication_timeout(settings: Any, ticket_keys: tuple[Any, Path]) -> None:
    _, public_path = ticket_keys
    current = replace(settings, ws_ticket_auth_timeout_seconds=0.05)
    app = create_app(
        current,
        token_validator=FakeTokenValidator(),
        access_checker=FakeAccessChecker(),
        ws_ticket_validator=SignedWebSocketTicketValidator(
            public_key_path=public_path,
            issuer="booking-orchestrator",
            audience="realtime-status-service",
            key_id="esb-1",
            max_ttl_seconds=60,
        ),
    )
    with TestClient(app) as client, pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect("/ws/bookings/BK-1", headers=ws_headers()) as websocket:
            websocket.receive_json()
    assert closed.value.code == CLOSE_AUTHENTICATION_TIMEOUT
