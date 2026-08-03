"""Application heartbeat with deterministic idle cleanup."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from datetime import UTC, datetime

from app.observability.metrics import HEARTBEAT_TIMEOUTS
from app.schemas.messages import HeartbeatControl
from app.websocket.connection_manager import Connection, ConnectionManager


class HeartbeatRunner:
    def __init__(
        self,
        manager: ConnectionManager,
        *,
        interval: float,
        idle_timeout: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._manager = manager
        self._interval = interval
        self._idle_timeout = idle_timeout
        self._clock = clock

    async def run(self, connection: Connection) -> None:
        try:
            while not connection.closed:
                await asyncio.sleep(self._interval)
                if self._clock() - connection.last_seen >= self._idle_timeout:
                    HEARTBEAT_TIMEOUTS.inc()
                    await self._manager.unregister(connection)
                    try:
                        await connection.websocket.close(code=1001, reason="heartbeat timeout")
                    except (RuntimeError, OSError):
                        pass
                    return
                payload = HeartbeatControl(timestamp=datetime.now(UTC)).model_dump(
                    by_alias=True, mode="json"
                )
                if not await self._manager.send(connection, payload):
                    return
        except asyncio.CancelledError:
            raise
