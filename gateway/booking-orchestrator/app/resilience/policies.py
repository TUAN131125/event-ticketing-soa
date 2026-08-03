from __future__ import annotations

import asyncio
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import TypeVar

from app.domain.errors import BusinessFault, DependencyFailure
from app.domain.models import RequestContext

T = TypeVar("T")


class RetryClass(str, Enum):
    NONE = "none"
    SAFE_READ = "safeRead"
    IDEMPOTENT_COMMAND = "idempotentCommand"
    RECONCILIATION_ONLY = "reconciliationOnly"
    SIDE_EFFECT = "sideEffectAtLeastOnce"


@dataclass
class CircuitBreaker:
    threshold: int
    recovery_seconds: float
    failures: int = 0
    opened_at: float | None = None

    def before_call(self) -> None:
        if self.opened_at is None:
            return
        if time.monotonic() - self.opened_at >= self.recovery_seconds:
            self.opened_at = None
            self.failures = 0
            return
        raise DependencyFailure("CIRCUIT_OPEN", "Dependency is temporarily unavailable.", 503, True)

    def success(self) -> None:
        self.failures = 0
        self.opened_at = None

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.opened_at = time.monotonic()


class Bulkhead:
    def __init__(self, limit: int) -> None:
        self._semaphore = asyncio.Semaphore(limit)

    async def run(self, call: Callable[[], Awaitable[T]]) -> T:
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=0.05)
        except asyncio.TimeoutError as exc:
            raise DependencyFailure("BULKHEAD_FULL", "Dependency capacity is exhausted.", 503, True) from exc
        try:
            return await call()
        finally:
            self._semaphore.release()


class ResilienceExecutor:
    def __init__(
        self,
        attempts: dict[RetryClass, int],
        base_delay: float,
        circuit: CircuitBreaker,
        bulkhead: Bulkhead,
    ) -> None:
        self.attempts, self.base_delay, self.circuit, self.bulkhead = (
            attempts,
            base_delay,
            circuit,
            bulkhead,
        )

    async def execute(
        self,
        call: Callable[[], Awaitable[T]],
        retry_class: RetryClass,
        context: RequestContext,
    ) -> T:
        attempts = self.attempts.get(retry_class, 1)
        last: Exception | None = None
        for attempt in range(1, attempts + 1):
            if time.monotonic() >= context.deadline_monotonic:
                raise DependencyFailure("REQUEST_DEADLINE_EXCEEDED", "Request deadline exceeded.", 503, True)
            self.circuit.before_call()
            try:
                remaining = max(0.001, context.deadline_monotonic - time.monotonic())
                result = await asyncio.wait_for(self.bulkhead.run(call), timeout=remaining)
                self.circuit.success()
                return result
            except BusinessFault:
                raise
            except Exception as exc:
                last = exc
                self.circuit.failure()
                if retry_class in {RetryClass.NONE, RetryClass.RECONCILIATION_ONLY} or attempt >= attempts:
                    raise
                delay = self.base_delay * (2 ** (attempt - 1)) + random.uniform(0, self.base_delay)
                if time.monotonic() + delay >= context.deadline_monotonic:
                    break
                await asyncio.sleep(delay)
        raise DependencyFailure("DEPENDENCY_UNAVAILABLE", "Dependency call failed.", 503, True) from last
