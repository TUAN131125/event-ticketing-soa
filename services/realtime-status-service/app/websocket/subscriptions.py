"""Bounded handshake limiter and connection limit policy."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict, deque
from collections.abc import Callable


class HandshakeRateLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: float,
        *,
        max_keys: int = 10000,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limit = limit
        self._window = window_seconds
        self._max_keys = max_keys
        self._clock = clock
        self._attempts: OrderedDict[str, deque[float]] = OrderedDict()
        self._lock = asyncio.Lock()

    async def allow(self, key: str) -> bool:
        now = self._clock()
        cutoff = now - self._window
        async with self._lock:
            bucket = self._attempts.setdefault(key, deque())
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            allowed = len(bucket) < self._limit
            bucket.append(now)
            self._attempts.move_to_end(key)
            while len(self._attempts) > self._max_keys:
                self._attempts.popitem(last=False)
            return allowed


class ConnectionLimitExceeded(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
