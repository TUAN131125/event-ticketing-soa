"""Notification outage must be inert: bookings still confirm and tickets still issue."""

from __future__ import annotations

import httpx

from tests.support.e2e import (
    Browser,
    Inventory,
    correlation_id,
    get_booking,
    place_booking,
    seat_status,
    service_stopped,
)


def test_booking_confirms_while_notification_is_down(
    client: httpx.Client, browser: Browser, inventory: Inventory
) -> None:
    seats = inventory.seat_ids[:1]
    correlation = correlation_id("notif-down")

    with service_stopped("notification"):
        response = place_booking(
            client, browser, inventory, seat_ids=seats, correlation=correlation
        )
        assert response.status_code == 201, (
            "notification delivery must never gate a booking result: "
            f"{response.status_code} {response.text}"
        )
        booking = response.json()
        assert booking["status"] == "CONFIRMED"
        assert booking["ticketIds"], "tickets are issued regardless of notification"
        assert booking["correlationId"] == correlation

        # Seat and booking authority are unaffected by the outage.
        assert seat_status(client, inventory.event_id, seats[0]) == "TAKEN"
        assert (
            get_booking(client, browser, booking["bookingId"])["status"] == "CONFIRMED"
        )

    # The booking is still confirmed after Notification comes back.
    assert get_booking(client, browser, booking["bookingId"])["status"] == "CONFIRMED"


def test_notification_outage_does_not_break_later_bookings(
    client: httpx.Client, browser: Browser, inventory: Inventory
) -> None:
    with service_stopped("notification"):
        first = place_booking(
            client, browser, inventory, seat_ids=inventory.seat_ids[:1]
        )
        assert first.status_code == 201, first.text

    second = place_booking(client, browser, inventory, seat_ids=inventory.seat_ids[1:2])
    assert second.status_code == 201, second.text
    assert second.json()["status"] == "CONFIRMED"
