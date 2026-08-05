"""Happy-path booking across the running ESB, Seat SOAP, Payment and Ticket containers."""

from __future__ import annotations

import httpx

from tests.support.e2e import (
    ESB_URL,
    Browser,
    Inventory,
    correlation_id,
    get_booking,
    place_booking,
    seat_status,
)


def test_confirmed_booking_has_payment_seat_ticket_and_correlation_evidence(
    client: httpx.Client, browser: Browser, inventory: Inventory
) -> None:
    correlation = correlation_id("book-success")
    seats = inventory.seat_ids[:2]

    response = place_booking(
        client, browser, inventory, seat_ids=seats, correlation=correlation
    )
    assert response.status_code == 201, response.text
    booking = response.json()

    assert booking["status"] == "CONFIRMED"
    assert booking["correlationId"] == correlation
    assert booking["paymentId"], "a confirmed booking must carry payment evidence"
    assert booking["reservationId"], "a confirmed booking must carry seat evidence"
    assert len(booking["ticketIds"]) == len(seats), "one ticket per booked seat"
    assert booking["total"]["currency"] == "VND"
    assert booking["total"]["amountMinor"] > 0

    # The authoritative read through the ESB agrees with the command result.
    reread = get_booking(client, browser, booking["bookingId"])
    assert reread["status"] == "CONFIRMED"
    assert reread["bookingId"] == booking["bookingId"]

    # Seat Inventory is authoritative: the booked seats are no longer available.
    for seat_id in seats:
        assert seat_status(client, inventory.event_id, seat_id) == "TAKEN"

    # An untouched seat from the same map stays available.
    assert (
        seat_status(client, inventory.event_id, inventory.seat_ids[-1]) == "AVAILABLE"
    )


def test_correlation_id_is_traceable_across_the_whole_workflow(
    client: httpx.Client, browser: Browser, inventory: Inventory
) -> None:
    correlation = correlation_id("book-trace")
    response = place_booking(
        client,
        browser,
        inventory,
        seat_ids=inventory.seat_ids[:1],
        correlation=correlation,
    )
    assert response.status_code == 201, response.text

    # The browser's correlation id survives the whole orchestration and is echoed on
    # both the response body and the response header.
    assert response.json()["correlationId"] == correlation
    assert response.headers["X-Correlation-ID"] == correlation

    booking_id = response.json()["bookingId"]
    reread = client.get(
        f"{ESB_URL}/api/bookings/{booking_id}",
        headers=browser.headers(correlation_id("trace-read")),
    )
    assert reread.status_code == 200, reread.text
    assert reread.json()["bookingId"] == booking_id

    # Workflow traces are an Admin/Ops projection; a customer must not read them.
    trace = client.get(
        f"{ESB_URL}/api/traces/{correlation}",
        headers=browser.headers(correlation_id("trace-deny")),
    )
    assert trace.status_code == 403, trace.text


def test_repeating_one_idempotency_key_never_books_twice(
    client: httpx.Client, browser: Browser, inventory: Inventory
) -> None:
    key = f"e2e-idem-{correlation_id('k')}"
    seats = inventory.seat_ids[:1]

    first = place_booking(
        client, browser, inventory, seat_ids=seats, idempotency_key=key
    )
    assert first.status_code == 201, first.text
    second = place_booking(
        client, browser, inventory, seat_ids=seats, idempotency_key=key
    )
    assert second.status_code in {200, 201}, second.text
    assert second.json()["bookingId"] == first.json()["bookingId"]
