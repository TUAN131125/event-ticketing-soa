"""Aggregate health service: probe every dependency concurrently, then apply policy."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence

from app.domain.errors import ProbeFailure
from app.domain.health import (
    AggregateHealth,
    AggregateState,
    DependencyHealth,
    DependencyState,
    evaluate,
)
from app.ports.providers import HealthProbe
from app.ports.repositories import Clock

ESB_PERSISTENCE = "esb-persistence"


class DatabaseProbe:
    """The ESB's own persistence, probed through the same interface as providers."""

    name = ESB_PERSISTENCE
    critical = True

    def __init__(self, database: object | None) -> None:
        self._database = database

    async def check(self, timeout_seconds: float) -> None:
        if self._database is None:
            return
        ping = getattr(self._database, "ping", None)
        if ping is None:
            return
        try:
            await asyncio.wait_for(ping(), timeout=timeout_seconds)
        except TimeoutError as exc:
            raise ProbeFailure("TIMEOUT") from exc
        except OSError as exc:
            raise ProbeFailure("UNREACHABLE") from exc
        except Exception as exc:  # noqa: BLE001 -- driver errors vary; the code stays safe
            raise ProbeFailure("NOT_READY") from exc


class HealthService:
    def __init__(self, probes: Sequence[HealthProbe], clock: Clock, timeout_seconds: float) -> None:
        self._probes = tuple(probes)
        self._clock = clock
        self._timeout_seconds = timeout_seconds

    async def aggregate(self) -> AggregateHealth:
        results = await asyncio.gather(*(self._probe(probe) for probe in self._probes))
        return AggregateHealth(
            status=self._status(results),
            checked_at=self._clock.now(),
            dependencies=tuple(results),
        )

    async def _probe(self, probe: HealthProbe) -> DependencyHealth:
        started = time.perf_counter()
        try:
            await asyncio.wait_for(
                probe.check(self._timeout_seconds),
                timeout=self._timeout_seconds,
            )
        except ProbeFailure as failure:
            return self._down(probe, started, failure.code)
        except TimeoutError:
            return self._down(probe, started, "TIMEOUT")
        return DependencyHealth(
            name=probe.name,
            critical=probe.critical,
            state=DependencyState.UP,
            latency_ms=self._elapsed_ms(started),
        )

    def _down(self, probe: HealthProbe, started: float, error_code: str) -> DependencyHealth:
        return DependencyHealth(
            name=probe.name,
            critical=probe.critical,
            state=DependencyState.DOWN,
            latency_ms=self._elapsed_ms(started),
            error_code=error_code,
        )

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, int((time.perf_counter() - started) * 1000))

    @staticmethod
    def _status(results: Sequence[DependencyHealth]) -> AggregateState:
        return evaluate(results)
