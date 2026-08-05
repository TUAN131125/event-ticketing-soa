from __future__ import annotations

import time
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.websocket.endpoint import CLOSE_FORBIDDEN, CLOSE_UNAUTHENTICATED
from tests.conftest import ws_headers


def _authenticate(client: TestClient, ticket: str, booking_id: str = "BK-1") -> dict:
    with client.websocket_connect(f"/ws/bookings/{booking_id}", headers=ws_headers()) as websocket:
        websocket.send_json({"type": "authenticate", "ticket": ticket})
        authenticated = websocket.receive_json()
        connected = websocket.receive_json()
    assert authenticated["type"] == "authenticated"
    return connected


def test_valid_ticket_connects(client: TestClient, issue_ticket: Callable[..., str]) -> None:
    assert _authenticate(client, issue_ticket())["type"] == "connected"


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 1, "iat": int(time.time()) - 30},
        {"iss": "wrong"},
        {"aud": "wrong"},
        {"scope": "wrong"},
        {"bookingId": "BK-2"},
        {"iat": int(time.time()), "exp": int(time.time()) + 61},
    ],
)
def test_invalid_ticket_claims_are_rejected(
    client: TestClient,
    issue_ticket: Callable[..., str],
    overrides: dict[str, object],
) -> None:
    with pytest.raises(WebSocketDisconnect) as closed:
        _authenticate(client, issue_ticket(**overrides))
    assert closed.value.code == CLOSE_UNAUTHENTICATED


def test_ticket_is_bound_to_authorized_booking(
    client: TestClient, issue_ticket: Callable[..., str]
) -> None:
    with pytest.raises(WebSocketDisconnect) as closed:
        _authenticate(client, issue_ticket(bookingId="BK-1"), booking_id="BK-2")
    assert closed.value.code == CLOSE_UNAUTHENTICATED


def test_ticket_jti_is_single_use(client: TestClient, issue_ticket: Callable[..., str]) -> None:
    signed = issue_ticket(jti="single-use-jti")
    assert _authenticate(client, signed)["type"] == "connected"
    with pytest.raises(WebSocketDisconnect) as closed:
        _authenticate(client, signed)
    assert closed.value.code == CLOSE_FORBIDDEN
