"""Concurrent, booking-isolated WebSocket connection registry."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from starlette.websockets import WebSocketDisconnect

from app.observability.metrics import ACTIVE_CONNECTIONS, DEAD_CONNECTIONS
from app.websocket.subscriptions import ConnectionLimitExceeded


class WebSocketLike(Protocol):
    async def accept(self, subprotocol: str | None = None) -> None: ...
    async def send_json(self, data: Any) -> None: ...
    async def close(self, code: int = 1000, reason: str | None = None) -> None: ...


@dataclass(eq=False, slots=True)
class Connection:
    websocket: WebSocketLike
    booking_id: str
    principal_id: str
    client_ip: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    last_seen: float = field(default_factory=time.monotonic)
    closed: bool = False

    def __hash__(self) -> int:
        return hash(self.id)


@dataclass(frozen=True, slots=True)
class BroadcastResult:
    subscribers: int
    delivered: int
    removed: int


class ConnectionManager:
    def __init__(
        self, *, max_connections: int, max_per_principal: int, max_per_ip: int, send_timeout: float
    ) -> None:
        self._max_connections = max_connections
        self._max_per_principal = max_per_principal
        self._max_per_ip = max_per_ip
        self._send_timeout = send_timeout
        self._channels: dict[str, set[Connection]] = {}
        self._connections: dict[str, Connection] = {}
        self._principal_counts: dict[str, int] = {}
        self._ip_counts: dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._draining = False

    async def register(
        self,
        websocket: WebSocketLike,
        *,
        booking_id: str,
        principal_id: str,
        client_ip: str,
        subprotocol: str | None = None,
        accept_socket: bool = True,
    ) -> Connection:
        async with self._lock:
            if self._draining:
                raise ConnectionLimitExceeded("draining")
            if len(self._connections) >= self._max_connections:
                raise ConnectionLimitExceeded("service_limit")
            if self._principal_counts.get(principal_id, 0) >= self._max_per_principal:
                raise ConnectionLimitExceeded("principal_limit")
            if self._ip_counts.get(client_ip, 0) >= self._max_per_ip:
                raise ConnectionLimitExceeded("ip_limit")
            if accept_socket:
                await websocket.accept(subprotocol=subprotocol)
            connection = Connection(websocket, booking_id, principal_id, client_ip)
            self._connections[connection.id] = connection
            self._channels.setdefault(booking_id, set()).add(connection)
            self._principal_counts[principal_id] = self._principal_counts.get(principal_id, 0) + 1
            self._ip_counts[client_ip] = self._ip_counts.get(client_ip, 0) + 1
            ACTIVE_CONNECTIONS.set(len(self._connections))
            return connection

    async def unregister(self, connection: Connection) -> bool:
        async with self._lock:
            if self._connections.pop(connection.id, None) is None:
                return False
            connection.closed = True
            channel = self._channels.get(connection.booking_id)
            if channel is not None:
                channel.discard(connection)
                if not channel:
                    self._channels.pop(connection.booking_id, None)
            self._decrement(self._principal_counts, connection.principal_id)
            self._decrement(self._ip_counts, connection.client_ip)
            ACTIVE_CONNECTIONS.set(len(self._connections))
            return True

    @staticmethod
    def _decrement(counts: dict[str, int], key: str) -> None:
        value = counts.get(key, 0) - 1
        if value <= 0:
            counts.pop(key, None)
        else:
            counts[key] = value

    async def touch(self, connection: Connection, now: float | None = None) -> None:
        connection.last_seen = now if now is not None else time.monotonic()

    async def send(self, connection: Connection, payload: dict[str, Any]) -> bool:
        if connection.closed:
            return False
        try:
            await asyncio.wait_for(
                connection.websocket.send_json(payload), timeout=self._send_timeout
            )
            return True
        except (TimeoutError, RuntimeError, OSError, WebSocketDisconnect):
            DEAD_CONNECTIONS.labels("send_failure").inc()
            await self.unregister(connection)
            try:
                await connection.websocket.close(code=1011, reason="connection unavailable")
            except (RuntimeError, OSError, WebSocketDisconnect):
                pass
            return False

    async def broadcast(self, booking_id: str, payload: dict[str, Any]) -> BroadcastResult:
        async with self._lock:
            targets = tuple(self._channels.get(booking_id, ()))
        if not targets:
            return BroadcastResult(0, 0, 0)
        results = await asyncio.gather(*(self.send(connection, payload) for connection in targets))
        delivered = sum(results)
        return BroadcastResult(len(targets), delivered, len(targets) - delivered)

    async def stats(self) -> dict[str, int | bool]:
        async with self._lock:
            return {
                "activeConnections": len(self._connections),
                "activeBookingChannels": len(self._channels),
                "draining": self._draining,
            }

    async def begin_shutdown(self, control: dict[str, Any], close_code: int) -> None:
        async with self._lock:
            self._draining = True
            targets = tuple(self._connections.values())
        await asyncio.gather(
            *(self._shutdown_one(connection, control, close_code) for connection in targets),
            return_exceptions=True,
        )

    async def _shutdown_one(
        self, connection: Connection, control: dict[str, Any], close_code: int
    ) -> None:
        await self.send(connection, control)
        try:
            await asyncio.wait_for(
                connection.websocket.close(code=close_code, reason="service shutdown"),
                timeout=self._send_timeout,
            )
        except (TimeoutError, RuntimeError, OSError, WebSocketDisconnect):
            pass
        await self.unregister(connection)

    @property
    def draining(self) -> bool:
        return self._draining
