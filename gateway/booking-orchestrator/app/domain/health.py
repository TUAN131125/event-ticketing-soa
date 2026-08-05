"""Aggregate health domain model and the policy that combines dependency states."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DependencyState(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


class AggregateState(str, Enum):
    UP = "UP"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


@dataclass(frozen=True, slots=True)
class DependencyHealth:
    """One probed dependency. `error_code` is a stable code, never a provider message."""

    name: str
    critical: bool
    state: DependencyState
    latency_ms: int | None = None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class AggregateHealth:
    status: AggregateState
    checked_at: datetime
    dependencies: tuple[DependencyHealth, ...]

    @property
    def http_status(self) -> int:
        return 503 if self.status is AggregateState.DOWN else 200


def evaluate(dependencies: Sequence[DependencyHealth]) -> AggregateState:
    """A critical dependency down means DOWN; a noncritical one means DEGRADED."""
    if any(item.critical and item.state is DependencyState.DOWN for item in dependencies):
        return AggregateState.DOWN
    if any(item.state is DependencyState.DOWN for item in dependencies):
        return AggregateState.DEGRADED
    return AggregateState.UP
