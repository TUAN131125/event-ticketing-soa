"""Single-use WebSocket ticket replay stores."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, Protocol

from redis.exceptions import RedisError


class TicketReplayStore(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def consume(self, jti: str, expires_at: int) -> bool: ...


class InMemoryTicketReplayStore:
    """Bounded single-process store; Redis is used when replicas are configured."""

    def __init__(self, max_entries: int, clock: Callable[[], float] = time.time) -> None:
        self._max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[str, float] = OrderedDict()
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        async with self._lock:
            self._entries.clear()

    async def consume(self, jti: str, expires_at: int) -> bool:
        digest = hashlib.sha256(jti.encode("utf-8")).hexdigest()
        now = self._clock()
        async with self._lock:
            for key, expiry in tuple(self._entries.items()):
                if expiry <= now:
                    self._entries.pop(key, None)
            if digest in self._entries or expires_at <= now:
                return False
            if len(self._entries) >= self._max_entries:
                return False
            self._entries[digest] = float(expires_at)
            self._entries.move_to_end(digest)
            return True


class RedisTicketReplayStore:
    """Cross-replica atomic replay protection using SET NX EX."""

    def __init__(self, redis_url: str) -> None:
        self._url = redis_url
        self._redis: Any | None = None

    async def start(self) -> None:
        import redis.asyncio as redis

        self._redis = redis.from_url(
            self._url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
        )
        await self._redis.ping()

    async def stop(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def consume(self, jti: str, expires_at: int) -> bool:
        if self._redis is None:
            return False
        ttl = expires_at - int(time.time())
        if ttl <= 0:
            return False
        digest = hashlib.sha256(jti.encode("utf-8")).hexdigest()
        try:
            result = await self._redis.set(f"realtime:ws-ticket:{digest}", "1", nx=True, ex=ttl)
        except (OSError, RedisError):
            return False
        return bool(result)
