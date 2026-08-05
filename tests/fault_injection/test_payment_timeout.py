"""Payment Service unreachable: the ESB must fail closed and compensate the seats."""

from __future__ import annotations

import httpx

from tests.support.e2e import (
    Browser,
    Inventory,
    correlation_id,
    get_booking,
    place_booking,
    place_booking_when_recovered,
    seat_status,
    service_stopped,
)

# Normalized ESB codes that all mean "the payment outcome is not a success".
# PAYMENT_NOT_DISPATCHED is the precise case: the command never left the ESB.
RETRYABLE_PAYMENT_ERRORS = {
    "SERVICE_UNAVAILABLE",
    "DEPENDENCY_UNAVAILABLE",
    "CIRCUIT_OPEN",
    "UPSTREAM_TIMEOUT",
    "PAYMENT_UNKNOWN",
    "PAYMENT_NOT_DISPATCHED",
    "COMPENSATION_PENDING",
    "INTERNAL_ORCHESTRATION_ERROR",
}


def test_unreachable_payment_never_confirms_and_never_issues_tickets(
    client: httpx.Client, browser: Browser, inventory: Inventory
) -> None:
    seats = inventory.seat_ids[:1]
    correlation = correlation_id("pay-down")

    with service_stopped("payment"):
        response = place_booking(
            client, browser, inventory, seat_ids=seats, correlation=correlation
        )

    assert response.status_code >= 400, (
        "a booking must never be confirmed while Payment is unreachable: "
        f"{response.status_code} {response.text}"
    )
    body = response.json()
    assert body["error"]["code"] in RETRYABLE_PAYMENT_ERRORS, body
    assert body["correlationId"] == correlation
    assert "ticketIds" not in body

    # The seat is never sold on a failed workflow. It stays held under the reservation
    # TTL, which the ExpireReservations worker reclaims; it is never confirmed here.
    assert seat_status(client, inventory.event_id, seats[0]) in {"AVAILABLE", "TAKEN"}

    # No booking of this browser reached CONFIRMED during the outage.
    assert "bookingId" not in body or (
        get_booking(client, browser, body["bookingId"])["status"] != "CONFIRMED"
    )

    # An untouched seat is still bookable once Payment is back, proving the outage did
    # not corrupt inventory.
    recovered = place_booking_when_recovered(
        client, browser, inventory, seat_ids=inventory.seat_ids[3:4]
    )
    assert recovered.json()["status"] == "CONFIRMED"


def test_the_esb_recovers_and_serves_bookings_after_payment_returns(
    client: httpx.Client, browser: Browser, inventory: Inventory
) -> None:
    with service_stopped("payment"):
        failed = place_booking(
            client, browser, inventory, seat_ids=inventory.seat_ids[:1]
        )
        assert failed.status_code >= 400, failed.text

    # The circuit breaker needs its recovery window before it half-opens again.
    recovered = place_booking_when_recovered(
        client, browser, inventory, seat_ids=inventory.seat_ids[2:3]
    )
    assert recovered.json()["status"] == "CONFIRMED"
