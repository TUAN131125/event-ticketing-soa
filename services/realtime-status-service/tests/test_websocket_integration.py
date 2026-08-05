from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.websocket.endpoint import CLOSE_INVALID_ORIGIN, CLOSE_UNAUTHENTICATED
from tests.conftest import event, ws_headers


def _authenticate(websocket, ticket: str) -> None:
    websocket.send_json({"type": "authenticate", "ticket": ticket})
    assert websocket.receive_json()["type"] == "authenticated"
    assert websocket.receive_json()["type"] == "connected"


def _receive_status_event(websocket) -> dict[str, object]:
    for _ in range(5):
        message = websocket.receive_json()
        if message.get("type") == "heartbeat":
            websocket.send_json({"type": "heartbeat_ack", "heartbeatId": message["heartbeatId"]})
            continue
        return message
    raise AssertionError("Status event was not received after heartbeat controls")


def test_missing_ticket_and_invalid_origin_are_rejected(
    client: TestClient, issue_ticket: Callable[..., str]
) -> None:
    with pytest.raises(WebSocketDisconnect) as missing:
        with client.websocket_connect("/ws/bookings/BK-1", headers=ws_headers()) as websocket:
            websocket.send_json({"type": "authenticate", "ticket": "invalid"})
            websocket.receive_json()
    assert missing.value.code == CLOSE_UNAUTHENTICATED
    with pytest.raises(WebSocketDisconnect) as origin:
        with client.websocket_connect(
            "/ws/bookings/BK-1", headers=ws_headers("https://evil.example")
        ):
            pass
    assert origin.value.code == CLOSE_INVALID_ORIGIN


def test_internal_event_is_broadcast_only_to_authorized_booking(
    client: TestClient,
    issue_ticket: Callable[..., str],
    internal_headers: Callable[[], dict[str, str]],
) -> None:
    with client.websocket_connect("/ws/bookings/BK-1", headers=ws_headers()) as websocket:
        _authenticate(websocket, issue_ticket())
        response = client.post("/internal/status-events", headers=internal_headers(), json=event())
        assert response.status_code == 202
        message = _receive_status_event(websocket)
        assert message["bookingId"] == "BK-1"
        assert message["sequence"] == 1


def test_duplicate_and_stale_events_are_not_accepted_twice(
    client: TestClient,
    internal_headers: Callable[[], dict[str, str]],
) -> None:
    first = client.post("/internal/status-events", headers=internal_headers(), json=event())
    duplicate = client.post("/internal/status-events", headers=internal_headers(), json=event())
    stale = client.post(
        "/internal/status-events",
        headers=internal_headers(),
        json=event(message_id="msg-2", sequence=1),
    )
    assert first.json()["outcome"] == "STALE"
    assert duplicate.json()["outcome"] == "DUPLICATE"
    assert stale.json()["outcome"] == "STALE"


def test_internal_http_requires_service_jwt(
    client: TestClient,
    internal_headers: Callable[[], dict[str, str]],
) -> None:
    assert client.post("/internal/status-events", json=event()).status_code == 401
    assert (
        client.post(
            "/internal/status-events",
            headers={"Authorization": "Bearer invalid"},
            json=event(),
        ).status_code
        == 401
    )
    assert client.post(
        "/internal/status-events", headers=internal_headers(), json=event()
    ).status_code in {200, 202}
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200
