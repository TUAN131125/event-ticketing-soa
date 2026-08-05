"""Aggregate health against the running stack, with real provider outages."""

from __future__ import annotations

import time

import httpx

from tests.support.e2e import ESB_URL, service_stopped, wait_until

# The probe budget plus request overhead; a hung provider must never exceed this.
HEALTH_DEADLINE_SECONDS = 15


def aggregate(client: httpx.Client) -> httpx.Response:
    return client.get(f"{ESB_URL}/api/health")


def dependency(body: dict[str, object], name: str) -> dict[str, object]:
    entries = [item for item in body["dependencies"] if item["name"] == name]  # type: ignore[index]
    assert entries, f"{name} must appear in the aggregate report"
    return entries[0]


def test_a_healthy_stack_reports_up_and_lists_every_dependency(
    client: httpx.Client,
) -> None:
    response = aggregate(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "UP"
    assert body["checkedAt"]
    names = {item["name"] for item in body["dependencies"]}
    assert {
        "esb-persistence",
        "customer-service",
        "event-service",
        "seat-inventory-service",
        "booking-service",
        "payment-service",
        "ticket-service",
        "notification-service",
        "realtime-status-service",
    } <= names


def test_a_noncritical_outage_degrades_without_failing_the_endpoint(
    client: httpx.Client,
) -> None:
    with service_stopped("notification"):
        wait_until(
            "aggregate health to observe the notification outage",
            lambda: aggregate(client).json()["status"] == "DEGRADED",
            timeout=60,
            interval=2,
        )
        response = aggregate(client)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["status"] == "DEGRADED"
        assert dependency(body, "notification-service")["status"] == "DOWN"
        assert dependency(body, "seat-inventory-service")["status"] == "UP"


def test_realtime_outage_also_only_degrades(client: httpx.Client) -> None:
    with service_stopped("realtime"):
        wait_until(
            "aggregate health to observe the realtime outage",
            lambda: aggregate(client).json()["status"] == "DEGRADED",
            timeout=60,
            interval=2,
        )
        response = aggregate(client)
        assert response.status_code == 200, response.text
        assert (
            dependency(response.json(), "realtime-status-service")["status"] == "DOWN"
        )


def test_a_critical_outage_reports_down_with_503(client: httpx.Client) -> None:
    for service, name in (
        ("seat", "seat-inventory-service"),
        ("payment", "payment-service"),
    ):
        with service_stopped(service):
            wait_until(
                f"aggregate health to observe the {service} outage",
                lambda: aggregate(client).status_code == 503,
                timeout=60,
                interval=2,
            )
            response = aggregate(client)
            body = response.json()
            assert response.status_code == 503, response.text
            assert body["status"] == "DOWN"
            assert dependency(body, name)["status"] == "DOWN"
            assert dependency(body, name)["errorCode"] in {
                "TIMEOUT",
                "UNREACHABLE",
                "NOT_READY",
            }

            # Readiness stays independent of providers so the ESB keeps serving reads.
            readiness = client.get(f"{ESB_URL}/health/ready")
            assert readiness.status_code == 200, readiness.text
            liveness = client.get(f"{ESB_URL}/health/live")
            assert liveness.status_code == 200, liveness.text


def test_health_never_leaks_internal_urls_or_exception_text(
    client: httpx.Client,
) -> None:
    with service_stopped("payment"):
        wait_until(
            "aggregate health to observe the payment outage",
            lambda: aggregate(client).status_code == 503,
            timeout=60,
            interval=2,
        )
        body = aggregate(client).text
    assert "http://" not in body
    assert "Traceback" not in body
    assert "Errno" not in body
    assert ":8005" not in body


def test_a_provider_outage_keeps_the_endpoint_within_its_deadline(
    client: httpx.Client,
) -> None:
    with service_stopped("payment"):
        started = time.perf_counter()
        response = aggregate(client)
        elapsed = time.perf_counter() - started
    assert response.status_code in {200, 503}
    assert elapsed < HEALTH_DEADLINE_SECONDS, (
        f"aggregate health took {elapsed:.1f}s; probes must be bounded and concurrent"
    )
