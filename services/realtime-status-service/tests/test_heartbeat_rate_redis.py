from __future__ import annotations

import json
from typing import Any

import pytest

from app.broadcast.backends import RedisBroadcastBackend
from app.websocket.connection_manager import ConnectionManager
from app.websocket.heartbeat import HeartbeatRunner
from app.websocket.subscriptions import HandshakeRateLimiter
from tests.conftest import event


class Socket:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.close_code: int | None = None

    async def accept(self, subprotocol: str | None = None) -> None:
        del subprotocol

    async def send_json(self, data: Any) -> None:
        self.messages.append(data)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        del reason
        self.close_code = code


@pytest.mark.asyncio
async def test_handshake_rate_limiter_uses_bounded_window() -> None:
    now = [0.0]
    limiter = HandshakeRateLimiter(2, 10, max_keys=2, clock=lambda: now[0])
    assert await limiter.allow("one") is True
    assert await limiter.allow("one") is True
    assert await limiter.allow("one") is False
    now[0] = 11
    assert await limiter.allow("one") is True
    await limiter.allow("two")
    await limiter.allow("three")
    assert len(limiter._attempts) == 2


@pytest.mark.asyncio
async def test_heartbeat_timeout_unregisters_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = ConnectionManager(
        max_connections=2, max_per_principal=2, max_per_ip=2, send_timeout=0.1
    )
    socket = Socket()
    connection = await manager.register(socket, booking_id="BK-1", principal_id="U1", client_ip="1")
    times = iter([0.0, 2.0])
    runner = HeartbeatRunner(manager, interval=0.001, idle_timeout=1, clock=lambda: next(times))
    connection.last_seen = 0
    await runner.run(connection)
    assert socket.close_code == 1001
    assert (await manager.stats())["activeConnections"] == 0


@pytest.mark.redis
@pytest.mark.asyncio
async def test_redis_delivery_path_deduplicates_without_real_server() -> None:
    manager = ConnectionManager(
        max_connections=2, max_per_principal=2, max_per_ip=2, send_timeout=0.1
    )
    socket = Socket()
    await manager.register(socket, booking_id="BK-1", principal_id="U1", client_ip="1")
    backend = RedisBroadcastBackend(
        manager,
        redis_url="redis://unused",
        channel="test",
        authoritative_url_template="/api/bookings/{bookingId}",
        dedup_ttl=60,
        dedup_max_entries=2,
    )
    raw = json.dumps({"event": event(), "sequenceGap": False, "expectedSequence": None})
    await backend._deliver(raw)
    await backend._deliver(raw)
    assert [item["messageId"] for item in socket.messages] == ["msg-1"]
