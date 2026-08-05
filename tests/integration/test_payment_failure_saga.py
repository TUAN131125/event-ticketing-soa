"""A declined payment must leave no ticket, no confirmed booking and no held seat."""

from __future__ import annotations

import httpx

from tests.support.e2e import (
    Browser,
    Inventory,
    correlation_id,
    place_booking,
    seat_status,
    wait_until,
)

# Payment Service declines any method token whose value starts with "decline".
DECLINED_TOKEN = "decline-e2e-token"


def test_declined_payment_releases_seats_and_never_issues_tickets(
    client: httpx.Client, browser: Browser, inventory: Inventory
) -> None:
    correlation = correlation_id("pay-decline")
    seats = inventory.seat_ids[:2]

    response = place_booking(
        client,
        browser,
        inventory,
        seat_ids=seats,
        payment_method_token=DECLINED_TOKEN,
        correlation=correlation,
    )
    assert response.status_code == 402, response.text
    body = response.json()
    # The ESB normalizes the provider's decline; PAYMENT_FAILED is also the reason
    # code carried into the canonical ReleaseSeats compensation.
    assert body["error"]["code"] == "PAYMENT_FAILED"
    assert body["correlationId"] == correlation

    # Compensation is asynchronous evidence-driven work; poll instead of sleeping.
    for seat_id in seats:
        wait_until(
            f"seat {seat_id} to be released after the declined payment",
            lambda seat_id=seat_id: seat_status(client, inventory.event_id, seat_id)
            == "AVAILABLE",
            timeout=60,
        )

    # The released seats are bookable again by a successful payment.
    retry = place_booking(client, browser, inventory, seat_ids=seats)
    assert retry.status_code == 201, retry.text
    assert retry.json()["status"] == "CONFIRMED"


def test_failed_booking_is_readable_and_carries_no_ticket_evidence(
    client: httpx.Client, browser: Browser, inventory: Inventory
) -> None:
    correlation = correlation_id("pay-evidence")
    response = place_booking(
        client,
        browser,
        inventory,
        seat_ids=inventory.seat_ids[:1],
        payment_method_token=DECLINED_TOKEN,
        correlation=correlation,
    )
    assert response.status_code == 402, response.text
    body = response.json()
    assert body["correlationId"] == correlation
    assert response.headers["X-Correlation-ID"] == correlation

    # A declined payment must not leak any downstream evidence to the browser.
    assert "ticketIds" not in body
    assert "reservationId" not in body
    assert "paymentId" not in body

    # The seat is compensated, so the same seat can be sold to someone else.
    wait_until(
        "the held seat to be released after the declined payment",
        lambda: seat_status(client, inventory.event_id, inventory.seat_ids[0])
        == "AVAILABLE",
        timeout=60,
    )
