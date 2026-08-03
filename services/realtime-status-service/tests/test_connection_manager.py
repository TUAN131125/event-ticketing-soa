from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.websocket.connection_manager import ConnectionManager
from app.websocket.subscriptions import ConnectionLimitExceeded


class FakeSocket:
    def __init__(self, *, fail_send: bool = False) -> None:
        self.accepted = False
        self.closed = False
        self.fail_send = fail_send
        self.messages: list[dict[str, Any]] = []

    async def accept(self, subprotocol: str | None = None) -> None:
        del subprotocol
        self.accepted = True

    async def send_json(self, data: Any) -> None:
        if self.fail_send:
            raise RuntimeError("dead")
        self.messages.append(data)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        del code, reason
        self.closed = True


def manager(**overrides: object) -> ConnectionManager:
    values = {"max_connections": 4, "max_per_principal": 2, "max_per_ip": 3, "send_timeout": 0.05}
    values.update(overrides)
    return ConnectionManager(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_register_unregister_is_idempotent_and_updates_stats() -> None:
    registry = manager()
    connection = await registry.register(
        FakeSocket(), booking_id="BK-1", principal_id="U1", client_ip="127.0.0.1"
    )
    assert (await registry.stats())["activeConnections"] == 1
    assert await registry.unregister(connection) is True
    assert await registry.unregister(connection) is False
    assert (await registry.stats())["activeConnections"] == 0


@pytest.mark.asyncio
async def test_multiple_subscribers_and_booking_isolation() -> None:
    registry = manager()
    first, second, other = FakeSocket(), FakeSocket(), FakeSocket()
    await registry.register(first, booking_id="BK-1", principal_id="U1", client_ip="1")
    await registry.register(second, booking_id="BK-1", principal_id="U2", client_ip="2")
    await registry.register(other, booking_id="BK-2", principal_id="U3", client_ip="3")
    result = await registry.broadcast("BK-1", {"messageId": "one"})
    assert result.delivered == 2
    assert first.messages == second.messages == [{"messageId": "one"}]
    assert other.messages == []


@pytest.mark.asyncio
async def test_send_failure_removes_dead_connection() -> None:
    registry = manager()
    dead = FakeSocket(fail_send=True)
    await registry.register(dead, booking_id="BK-1", principal_id="U1", client_ip="1")
    result = await registry.broadcast("BK-1", {"x": 1})
    assert result.removed == 1
    assert (await registry.stats())["activeConnections"] == 0


@pytest.mark.asyncio
async def test_connection_limits_and_shutdown() -> None:
    registry = manager(max_connections=2, max_per_principal=1)
    one = await registry.register(FakeSocket(), booking_id="BK-1", principal_id="U1", client_ip="1")
    with pytest.raises(ConnectionLimitExceeded, match="principal_limit"):
        await registry.register(FakeSocket(), booking_id="BK-1", principal_id="U1", client_ip="2")
    await registry.begin_shutdown({"type": "shutdown"}, 1012)
    assert one.closed
    assert (await registry.stats()) == {
        "activeConnections": 0,
        "activeBookingChannels": 0,
        "draining": True,
    }
    with pytest.raises(ConnectionLimitExceeded, match="draining"):
        await registry.register(FakeSocket(), booking_id="BK-2", principal_id="U2", client_ip="2")


@pytest.mark.asyncio
async def test_slow_connection_times_out_without_blocking_healthy_peer() -> None:
    class SlowSocket(FakeSocket):
        async def send_json(self, data: Any) -> None:
            await asyncio.sleep(1)

    registry = manager(send_timeout=0.01)
    slow, fast = SlowSocket(), FakeSocket()
    await registry.register(slow, booking_id="BK-1", principal_id="U1", client_ip="1")
    await registry.register(fast, booking_id="BK-1", principal_id="U2", client_ip="2")
    result = await registry.broadcast("BK-1", {"ok": True})
    assert result.delivered == 1
    assert fast.messages == [{"ok": True}]
