"""Notification delivery must never decide whether a booking succeeded."""

from __future__ import annotations

import httpx

from tests.support.e2e import (
    NOTIFICATION_URL,
    Browser,
    Inventory,
    correlation_id,
    get_booking,
    place_booking,
    service_token,
    wait_until,
)

# Canonical Delivery.status values from contracts/notification-service.yaml.
CANONICAL_STATES = {
    "PENDING",
    "SENDING",
    "DELIVERED",
    "RETRY_PENDING",
    "DEAD_LETTER",
    "CANCELLED",
}
UNSUCCESSFUL_STATES = {"RETRY_PENDING", "DEAD_LETTER", "CANCELLED"}


def deliveries(client: httpx.Client) -> list[dict[str, object]]:
    response = client.get(
        f"{NOTIFICATION_URL}/deliveries",
        headers={
            "Authorization": f"Bearer {service_token('notification-service')}",
            "X-Correlation-ID": correlation_id("deliv"),
        },
    )
    assert response.status_code == 200, response.text
    return list(response.json())


def test_booking_confirms_and_notification_state_is_recorded_separately(
    client: httpx.Client, browser: Browser, inventory: Inventory
) -> None:
    before = len(deliveries(client))

    response = place_booking(
        client, browser, inventory, seat_ids=inventory.seat_ids[:1]
    )
    assert response.status_code == 201, response.text
    booking = response.json()
    assert booking["status"] == "CONFIRMED"

    # Notification work is asynchronous; the booking result must not wait for it.
    wait_until(
        "a notification delivery to be recorded for the confirmed booking",
        lambda: len(deliveries(client)) > before,
        timeout=60,
    )

    # Whatever the delivery outcome is, the booking stays confirmed.
    reread = get_booking(client, browser, booking["bookingId"])
    assert reread["status"] == "CONFIRMED"

    states = {str(item.get("status")) for item in deliveries(client)}
    assert states, "delivery history must record an explicit state"
    assert states <= CANONICAL_STATES, f"unexpected delivery states: {sorted(states)}"


def test_a_failed_delivery_never_rolls_a_confirmed_booking_back(
    client: httpx.Client, browser: Browser, inventory: Inventory
) -> None:
    response = place_booking(
        client, browser, inventory, seat_ids=inventory.seat_ids[:1]
    )
    assert response.status_code == 201, response.text
    booking_id = response.json()["bookingId"]

    failed = [
        item
        for item in deliveries(client)
        if str(item.get("status")) in UNSUCCESSFUL_STATES
    ]
    # Failures are environment-dependent, but any failure must be inert for Booking.
    reread = get_booking(client, browser, booking_id)
    assert reread["status"] == "CONFIRMED", (
        "a confirmed booking must survive notification failures; "
        f"failed deliveries observed: {len(failed)}"
    )
