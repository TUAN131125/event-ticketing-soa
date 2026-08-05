from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

import pytest
import redis.asyncio as redis_asyncio
from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from starlette.websockets import WebSocketDisconnect

from app.broadcast.backends import BroadcastBackend
from app.main import create_app
from app.schemas.messages import RealtimeStatusEvent
from app.security.ticket_replay import RedisTicketReplayStore
from app.security.ws_ticket import ValidatedWebSocketTicket
from app.websocket.connection_manager import BroadcastResult
from app.websocket.endpoint import CLOSE_FORBIDDEN
from tests.conftest import ws_headers


class FakeRedisClient:
    def __init__(self, *, online: bool) -> None:
        self.online = online
        self.closed = False
        self.entries: set[str] = set()
        self.set_calls: list[dict[str, Any]] = []

    async def ping(self) -> bool:
        if not self.online:
            raise RedisError("unavailable")
        return True

    async def set(self, key: str, value: str, **kwargs: Any) -> bool:
        if not self.online:
            raise RedisError("unavailable")
        self.set_calls.append({"key": key, "value": value, **kwargs})
        if key in self.entries:
            return False
        self.entries.add(key)
        return True

    async def aclose(self) -> None:
        self.closed = True


class AvailableBroadcastBackend(BroadcastBackend):
    name = "test-memory"

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def publish(
        self,
        event: RealtimeStatusEvent,
        *,
        sequence_gap: bool = False,
        expected_sequence: int | None = None,
    ) -> BroadcastResult:
        del event, sequence_gap, expected_sequence
        return BroadcastResult(0, 0, 0)

    def ready(self) -> bool:
        return True

    def availability(self) -> str:
        return "available"


class AcceptTicketValidator:
    async def validate(self, ticket: str, booking_id: str) -> ValidatedWebSocketTicket:
        del ticket
        return ValidatedWebSocketTicket(
            subject="C001",
            booking_id=booking_id,
            jti="redis-ticket-jti",
            expires_at=int(time.time()) + 30,
        )


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_start_unavailable_is_non_throwing_and_consume_recovers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeRedisClient(online=False)
    monkeypatch.setattr(redis_asyncio, "from_url", lambda *args, **kwargs: client)
    store = RedisTicketReplayStore("redis://credential-not-logged@redis:6379/0")
    await store.start()
    assert store.available() is False
    assert await store.consume("first-jti", int(time.time()) + 30) is False
    client.online = True
    assert await store.consume("first-jti", int(time.time()) + 30) is True
    assert store.available() is True
    await store.stop()


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_client_creation_failure_is_non_throwing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_to_create(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        raise OSError("unavailable")

    monkeypatch.setattr(redis_asyncio, "from_url", fail_to_create)
    store = RedisTicketReplayStore("redis://redis:6379/0")
    await store.start()
    assert store.available() is False
    assert await store.consume("jti", int(time.time()) + 30) is False


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_set_nx_ex_accepts_once_and_rejects_reuse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = FakeRedisClient(online=True)
    monkeypatch.setattr(redis_asyncio, "from_url", lambda *args, **kwargs: client)
    store = RedisTicketReplayStore("redis://redis:6379/0")
    await store.start()
    expires_at = int(time.time()) + 30
    assert await store.consume("same-jti", expires_at) is True
    assert await store.consume("same-jti", expires_at) is False
    assert client.set_calls[0]["nx"] is True
    assert 0 < client.set_calls[0]["ex"] <= 30
    assert "same-jti" not in client.set_calls[0]["key"]
    await store.stop()


def test_optional_redis_keeps_http_up_but_ticket_replay_fails_closed(
    settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    redis_client = FakeRedisClient(online=False)
    monkeypatch.setattr(redis_asyncio, "from_url", lambda *args, **kwargs: redis_client)
    current = replace(settings, redis_url="redis://redis:6379/0", redis_required=False)
    app = create_app(
        current,
        broadcast_backend=AvailableBroadcastBackend(),
        ws_ticket_validator=AcceptTicketValidator(),
    )
    assert isinstance(app.state.ticket_replay_store, RedisTicketReplayStore)
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 200
        with pytest.raises(WebSocketDisconnect) as closed:
            with client.websocket_connect(
                "/ws/bookings/BK-1", headers=ws_headers()
            ) as ticket_socket:
                ticket_socket.send_json({"type": "authenticate", "ticket": "signed-ticket"})
                ticket_socket.receive_json()
        assert closed.value.code == CLOSE_FORBIDDEN


def test_required_redis_unavailable_is_not_ready(
    settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    redis_client = FakeRedisClient(online=False)
    monkeypatch.setattr(redis_asyncio, "from_url", lambda *args, **kwargs: redis_client)
    current = replace(settings, redis_url="redis://redis:6379/0", redis_required=True)
    app = create_app(
        current,
        broadcast_backend=AvailableBroadcastBackend(),
    )
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
