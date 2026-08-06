from __future__ import annotations

import asyncio
import random
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.domain.errors import DependencyError, EsbError

T = TypeVar("T")


class ResiliencePolicy:
    """Bounded retries, per-dependency bulkheads and a small circuit breaker."""

    def __init__(
        self,
        safe_attempts: int = 3,
        command_attempts: int = 2,
        bulkhead_limit: int = 20,
    ):
        self.safe_attempts = safe_attempts
        self.command_attempts = command_attempts
        self.failures: dict[str, deque[float]] = defaultdict(deque)
        self.open_until: dict[str, float] = {}
        self.bulkheads: dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(bulkhead_limit)
        )

    async def execute(
        self,
        name: str,
        call: Callable[[], Awaitable[T]],
        *,
        mode: str,
        deadline: float,
    ) -> T:
        now = time.monotonic()
        if self.open_until.get(name, 0) > now:
            raise DependencyError(
                "DEPENDENCY_CIRCUIT_OPEN", f"{name} circuit is open", 503, True
            )
        attempts = {
            "safe_read": self.safe_attempts,
            "idempotent_command": self.command_attempts,
            "side_effect": 1,
        }.get(mode, 1)
        last_error: Exception | None = None

        async with self.bulkheads[name]:
            for attempt in range(attempts):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise DependencyError(
                        "DEPENDENCY_TIMEOUT", "Request deadline exceeded", 504, True
                    )
                try:
                    result = await asyncio.wait_for(call(), timeout=remaining)
                    self.failures[name].clear()
                    return result
                except EsbError as exc:
                    if not exc.retryable:
                        raise
                    last_error = exc
                except (asyncio.TimeoutError, TimeoutError, OSError) as exc:
                    last_error = exc

                failures = self.failures[name]
                failures.append(time.monotonic())
                while failures and failures[0] < time.monotonic() - 30:
                    failures.popleft()
                if len(failures) >= 5:
                    self.open_until[name] = time.monotonic() + 20

                if attempt + 1 < attempts:
                    delay = min(0.05 * (2**attempt) + random.random() * 0.03, 0.5)
                    await asyncio.sleep(min(delay, max(0, deadline - time.monotonic())))

        raise DependencyError(
            "DEPENDENCY_UNAVAILABLE",
            f"{name} unavailable: {last_error}",
            503,
            True,
        )
