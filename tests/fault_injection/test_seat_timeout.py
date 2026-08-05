"""Seat Inventory unreachable: no booking may be confirmed without seat authority."""

from __future__ import annotations

import httpx

from tests.support.e2e import (
    ESB_URL,
    Browser,
    Inventory,
    correlation_id,
    place_booking,
    place_booking_when_recovered,
    seat_status,
    service_stopped,
)

# Normalized ESB codes for "seat authority is unreachable"; never a success.
SEAT_OUTAGE_ERRORS = {
    "SERVICE_UNAVAILABLE",
    "DEPENDENCY_UNAVAILABLE",
    "CIRCUIT_OPEN",
    "SEAT_UNAVAILABLE",
    "UPSTREAM_TIMEOUT",
    "INTERNAL_ORCHESTRATION_ERROR",
}


def test_seat_outage_fails_closed_with_a_normalized_error(
    client: httpx.Client, browser: Browser, inventory: Inventory
) -> None:
    correlation = correlation_id("seat-down")

    with service_stopped("seat"):
        response = place_booking(
            client,
            browser,
            inventory,
            seat_ids=inventory.seat_ids[:1],
            correlation=correlation,
        )
        assert response.status_code >= 500, (
            "the ESB must not invent seat authority while Seat Inventory is down: "
            f"{response.status_code} {response.text}"
        )
        body = response.json()
        assert body["error"]["code"] in SEAT_OUTAGE_ERRORS, body
        assert body["correlationId"] == correlation
        assert "reservationId" not in body

        # The ESB itself stays up and answers; it does not crash on a provider outage.
        # (`GET /api/health` currently reports only the ESB's own persistence, not the
        # providers, so it is not asserted as an outage signal here.)
        assert client.get(f"{ESB_URL}/health/live").status_code == 200

    # No seat was consumed by the failed attempt.
    for seat_id in inventory.seat_ids:
        assert seat_status(client, inventory.event_id, seat_id) == "AVAILABLE"


def test_bookings_succeed_again_once_seat_inventory_returns(
    client: httpx.Client, browser: Browser, inventory: Inventory
) -> None:
    with service_stopped("seat"):
        blocked = place_booking(
            client, browser, inventory, seat_ids=inventory.seat_ids[:1]
        )
        assert blocked.status_code >= 500, blocked.text

    # The circuit breaker needs its recovery window before it half-opens again.
    recovered = place_booking_when_recovered(
        client, browser, inventory, seat_ids=inventory.seat_ids[:1]
    )
    assert recovered.json()["status"] == "CONFIRMED"
    assert seat_status(client, inventory.event_id, inventory.seat_ids[0]) == "TAKEN"
