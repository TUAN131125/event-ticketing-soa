from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque

from app.domain.errors import EsbError


class SlidingWindowLimiter:
    """In-process ingress limiter for low-volume lab endpoints.

    Production deployments with multiple replicas should place an equivalent
    distributed limiter at the edge or replace this store with Redis.
    """

    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def check(self, key: str, limit: int, window: int) -> None:
        now = time.monotonic()
        async with self._lock:
            bucket = self._buckets[key]
            cutoff = now - window
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()

            if len(bucket) >= limit:
                retry_after = max(1, int(window - (now - bucket[0])))
                raise EsbError(
                    "RATE_LIMITED",
                    "Too many requests",
                    429,
                    True,
                    {"retryAfter": retry_after},
                )
            bucket.append(now)
