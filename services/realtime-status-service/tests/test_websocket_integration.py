from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.websocket.endpoint import CLOSE_FORBIDDEN, CLOSE_INVALID_ORIGIN, CLOSE_UNAUTHENTICATED
from tests.conftest import event, internal_headers, ws_headers


def connect(
    client: TestClient,
    booking_id: str = "BK-1",
    token: str = "owner-token",
    *,
    last_sequence: int | None = None,
):  # type: ignore[no-untyped-def]
    suffix = f"?lastSequence={last_sequence}" if last_sequence is not None else ""
    return client.websocket_connect(
        f"/ws/bookings/{booking_id}{suffix}",
        headers=ws_headers(),
        subprotocols=["bearer", token],
    )


def test_missing_invalid_token_and_origin_are_rejected(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as missing:
        with client.websocket_connect("/ws/bookings/BK-1", headers=ws_headers()) as websocket:
            websocket.receive_json()
    assert missing.value.code == CLOSE_UNAUTHENTICATED
    with pytest.raises(WebSocketDisconnect) as invalid:
        with connect(client, token="invalid"):
            pass
    assert invalid.value.code == CLOSE_UNAUTHENTICATED
    with pytest.raises(WebSocketDisconnect) as origin:
        with client.websocket_connect(
            "/ws/bookings/BK-1",
            headers=ws_headers("https://evil.example"),
            subprotocols=["bearer", "owner-token"],
        ):
            pass
    assert origin.value.code == CLOSE_INVALID_ORIGIN


def test_non_owner_rejected_owner_and_admin_accepted(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as denied:
        with connect(client, token="other-token"):
            pass
    assert denied.value.code == CLOSE_FORBIDDEN
    with connect(client) as owner:
        assert owner.receive_json()["type"] == "connected"
    with connect(client, booking_id="BK-ADMIN", token="admin-token") as admin:
        assert admin.receive_json()["type"] == "connected"


def test_internal_event_broadcast_is_booking_isolated(client: TestClient) -> None:
    with connect(client, "BK-1") as wanted, connect(client, "BK-2") as other:
        assert wanted.receive_json()["type"] == "connected"
        assert other.receive_json()["type"] == "connected"
        response = client.post("/internal/status-events", headers=internal_headers(), json=event())
        assert response.status_code == 202
        assert response.json()["outcome"] == "accepted"
        assert wanted.receive_json()["bookingId"] == "BK-1"
        assert other.receive_json()["type"] == "heartbeat"


def test_two_tabs_receive(client: TestClient) -> None:
    with connect(client) as first, connect(client) as second:
        first.receive_json()
        second.receive_json()
        response = client.post(
            "/internal/status-events", headers=internal_headers(), json=event(message_id="two-tabs")
        )
        assert response.status_code == 202
        assert first.receive_json()["messageId"] == "two-tabs"
        assert second.receive_json()["messageId"] == "two-tabs"
        assert client.get("/connections/health").json()["activeConnections"] == 2


def test_disconnect_cleanup(client: TestClient) -> None:
    with connect(client) as socket:
        assert socket.receive_json()["type"] == "connected"
        assert client.get("/connections/health").json()["activeConnections"] == 1
    deadline = time.monotonic() + 0.5
    while (
        client.get("/connections/health").json()["activeConnections"]
        and time.monotonic() < deadline
    ):
        time.sleep(0.005)
    assert client.get("/connections/health").json()["activeConnections"] == 0


def test_duplicate_and_out_of_order_are_not_rebroadcast(client: TestClient) -> None:
    with connect(client) as socket:
        socket.receive_json()
        first = client.post(
            "/internal/status-events",
            headers=internal_headers(),
            json=event(message_id="dedup", sequence=1),
        )
        duplicate = client.post(
            "/internal/status-events",
            headers=internal_headers(),
            json=event(message_id="dedup", sequence=1),
        )
        stale = client.post(
            "/internal/status-events",
            headers=internal_headers(),
            json=event(message_id="stale", sequence=1),
        )
        assert first.json()["outcome"] == "accepted"
        assert duplicate.json()["outcome"] == "duplicate"
        assert stale.json()["outcome"] == "stale"
        assert socket.receive_json()["messageId"] == "dedup"
        assert socket.receive_json()["type"] == "heartbeat"


def test_sequence_gap_signals_resync_before_event(client: TestClient) -> None:
    with connect(client) as socket:
        socket.receive_json()
        response = client.post(
            "/internal/status-events",
            headers=internal_headers(),
            json=event(message_id="gap", sequence=3),
        )
        assert response.json()["sequenceGap"] is True
        resync = socket.receive_json()
        assert resync["type"] == "resync_required"
        assert resync["reason"] == "sequence_gap"
        assert resync["authoritativeUrl"] == "/api/bookings/BK-1"
        assert socket.receive_json()["messageId"] == "gap"


def test_reconnect_always_requires_authoritative_rest_resync(client: TestClient) -> None:
    with connect(client, last_sequence=4) as socket:
        assert socket.receive_json()["type"] == "connected"
        message = socket.receive_json()
        assert message["type"] == "resync_required"
        assert message["reason"] == "reconnect_no_replay"
        assert message["authoritativeUrl"] == "/api/bookings/BK-1"


def test_heartbeat_closes_unresponsive_client(client: TestClient) -> None:
    with connect(client) as socket:
        socket.receive_json()
        heartbeats = 0
        close_code = None
        for _ in range(6):
            try:
                assert socket.receive_json()["type"] == "heartbeat"
                heartbeats += 1
            except WebSocketDisconnect as closed:
                close_code = closed.code
                break
        assert heartbeats >= 1
        assert close_code == 1001


def test_internal_auth_validation_size_health_and_no_redis(client: TestClient) -> None:
    assert client.post("/internal/status-events", json=event()).status_code == 401
    assert (
        client.post(
            "/internal/status-events", headers=internal_headers("wrong"), json=event()
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/internal/status-events", headers=internal_headers(caller="browser"), json=event()
        ).status_code
        == 403
    )
    extra = {**event(), "unexpected": True}
    assert (
        client.post("/internal/status-events", headers=internal_headers(), json=extra).status_code
        == 422
    )
    too_large = {**event(), "message": "x" * 2000}
    assert (
        client.post(
            "/internal/status-events", headers=internal_headers(), json=too_large
        ).status_code
        == 413
    )
    assert client.get("/health/live").status_code == 200
    assert client.get("/health/ready").status_code == 200
    health = client.get("/connections/health").json()
    assert health["broadcastBackend"] == "memory"
    assert health["redisAvailability"] == "not_configured"
    assert "realtime_readiness" in client.get("/metrics").text
