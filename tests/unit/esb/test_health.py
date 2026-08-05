"""Aggregate health: probe fan-out, policy, timeout bounds and safe output."""

from __future__ import annotations

import asyncio
import time

import httpx
import pytest
from app.adapters.health import ReadinessProbe
from app.application.health import DatabaseProbe, HealthService
from app.domain.errors import ProbeFailure
from app.domain.health import (
    AggregateState,
    DependencyHealth,
    DependencyState,
    evaluate,
)
from fakes import FakeClock


class StubProbe:
    def __init__(
        self, name: str, *, critical: bool, failure: str | None = None
    ) -> None:
        self.name = name
        self.critical = critical
        self._failure = failure
        self.calls = 0

    async def check(self, timeout_seconds: float) -> None:
        self.calls += 1
        if self._failure is not None:
            raise ProbeFailure(self._failure)


class HangingProbe:
    name = "slow-service"
    critical = True

    async def check(self, timeout_seconds: float) -> None:
        await asyncio.sleep(60)


def up(name: str, *, critical: bool) -> DependencyHealth:
    return DependencyHealth(name, critical, DependencyState.UP)


def down(name: str, *, critical: bool) -> DependencyHealth:
    return DependencyHealth(name, critical, DependencyState.DOWN, error_code="TIMEOUT")


def test_policy_maps_dependency_states_to_one_aggregate_state() -> None:
    assert (
        evaluate([up("a", critical=True), up("b", critical=False)]) is AggregateState.UP
    )
    assert (
        evaluate([up("a", critical=True), down("notification", critical=False)])
        is AggregateState.DEGRADED
    )
    assert (
        evaluate([down("seat", critical=True), up("notification", critical=False)])
        is AggregateState.DOWN
    )
    # A critical failure outranks a noncritical one.
    assert (
        evaluate([down("payment", critical=True), down("realtime", critical=False)])
        is AggregateState.DOWN
    )
    assert evaluate([]) is AggregateState.UP


@pytest.mark.asyncio
async def test_all_dependencies_up_reports_up_with_http_200() -> None:
    service = HealthService(
        [StubProbe("seat-inventory-service", critical=True)], FakeClock(), 1.0
    )
    report = await service.aggregate()
    assert report.status is AggregateState.UP
    assert report.http_status == 200
    assert report.dependencies[0].state is DependencyState.UP
    assert report.dependencies[0].latency_ms is not None


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["notification-service", "realtime-status-service"])
async def test_a_noncritical_outage_degrades_but_keeps_http_200(name: str) -> None:
    service = HealthService(
        [
            StubProbe("seat-inventory-service", critical=True),
            StubProbe(name, critical=False, failure="UNREACHABLE"),
        ],
        FakeClock(),
        1.0,
    )
    report = await service.aggregate()
    assert report.status is AggregateState.DEGRADED
    assert report.http_status == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["seat-inventory-service", "payment-service"])
async def test_a_critical_outage_reports_down_with_http_503(name: str) -> None:
    service = HealthService(
        [
            StubProbe(name, critical=True, failure="UNREACHABLE"),
            StubProbe("notification-service", critical=False),
        ],
        FakeClock(),
        1.0,
    )
    report = await service.aggregate()
    assert report.status is AggregateState.DOWN
    assert report.http_status == 503
    failed = next(item for item in report.dependencies if item.name == name)
    assert failed.error_code == "UNREACHABLE"


@pytest.mark.asyncio
async def test_probes_run_concurrently_and_never_retry() -> None:
    probes = [StubProbe(f"service-{index}", critical=True) for index in range(5)]
    service = HealthService(probes, FakeClock(), 1.0)
    await service.aggregate()
    assert all(probe.calls == 1 for probe in probes), "a health request must not retry"


@pytest.mark.asyncio
async def test_a_hanging_dependency_is_bounded_by_the_configured_timeout() -> None:
    service = HealthService([HangingProbe()], FakeClock(), 0.05)
    started = time.perf_counter()
    report = await service.aggregate()
    elapsed = time.perf_counter() - started
    assert elapsed < 5, "the endpoint must not wait for a hung dependency"
    assert report.status is AggregateState.DOWN
    assert report.dependencies[0].error_code == "TIMEOUT"


@pytest.mark.asyncio
async def test_probe_reports_stable_codes_and_never_provider_internals() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/health/ready"):
            return httpx.Response(503, text="psycopg OperationalError at 10.0.0.7:5432")
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        probe = ReadinessProbe(
            "payment-service", "http://payment.internal:8005", http, critical=True
        )
        with pytest.raises(ProbeFailure) as failure:
            await probe.check(1.0)
    assert failure.value.code == "NOT_READY"
    assert "10.0.0.7" not in failure.value.code
    assert "payment.internal" not in failure.value.code


@pytest.mark.asyncio
async def test_unreachable_dependency_is_reported_as_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        probe = ReadinessProbe(
            "seat-inventory-service", "http://seat:8003", http, critical=True
        )
        with pytest.raises(ProbeFailure) as failure:
            await probe.check(1.0)
    assert failure.value.code == "UNREACHABLE"


@pytest.mark.asyncio
async def test_database_probe_reports_esb_persistence_failure() -> None:
    class BrokenDatabase:
        async def ping(self) -> None:
            raise OSError("socket closed")

    service = HealthService([DatabaseProbe(BrokenDatabase())], FakeClock(), 1.0)
    report = await service.aggregate()
    assert report.status is AggregateState.DOWN
    assert report.http_status == 503
    assert report.dependencies[0].name == "esb-persistence"
    assert report.dependencies[0].error_code == "UNREACHABLE"
