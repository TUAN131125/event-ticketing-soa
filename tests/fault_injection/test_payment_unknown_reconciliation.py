"""A dispatched payment command whose answer is lost must reconcile, never guess.

The Payment container is frozen rather than stopped, so the request really leaves the
ESB and the outcome is genuinely unknown. Nothing here is mocked.
"""

from __future__ import annotations

import time

import httpx

from tests.support.e2e import (
    ESB_URL,
    Browser,
    Inventory,
    correlation_id,
    get_booking,
    place_booking,
    seat_status,
    service_paused,
    service_stopped,
    wait_until,
)

UNRESOLVED_BOOKING_STATES = {"PENDING", "SEAT_RESERVED", "PAYMENT_PROCESSING"}
# Long enough to span several reconciliation worker cycles.
OBSERVATION_SECONDS = 30
SAMPLE_INTERVAL_SECONDS = 3


def test_a_lost_payment_answer_returns_202_and_never_releases_the_seat(
    client: httpx.Client, browser: Browser, inventory: Inventory
) -> None:
    seats = inventory.seat_ids[:1]
    correlation = correlation_id("pay-lost")

    with service_paused("payment"):
        response = place_booking(
            client, browser, inventory, seat_ids=seats, correlation=correlation
        )

    assert response.status_code == 202, (
        "an unknown payment outcome must be accepted for reconciliation, not failed: "
        f"{response.status_code} {response.text}"
    )
    body = response.json()
    assert body["correlationId"] == correlation
    assert body["bookingId"]
    assert response.headers["Location"] == f"/api/bookings/{body['bookingId']}"
    assert int(response.headers["Retry-After"]) >= 1

    # The ESB must not guess: no ticket, no confirmation, and the seat stays held.
    assert not body.get("ticketIds")
    assert body["status"] in UNRESOLVED_BOOKING_STATES
    assert seat_status(client, inventory.event_id, seats[0]) == "TAKEN"

    booking = get_booking(client, browser, body["bookingId"])
    assert booking["status"] != "CONFIRMED"
    assert booking["status"] != "FAILED", "an unknown outcome is not a failure"


def test_reconciliation_never_guesses_and_never_charges_twice(
    client: httpx.Client, browser: Browser, inventory: Inventory
) -> None:
    """The worker polls Payment; while Payment is not authoritative it must wait.

    A payment frozen mid-create resumes as PENDING, which is not a terminal outcome.
    The worker must therefore keep retrying under its deadline rather than declare the
    booking failed or confirmed, and it must never re-issue the command under a new key.
    """
    seats = inventory.seat_ids[:1]

    with service_paused("payment"):
        response = place_booking(client, browser, inventory, seat_ids=seats)
    assert response.status_code == 202, response.text
    booking_id = response.json()["bookingId"]

    # Sample the invariant across many worker cycles instead of waiting for a signal.
    deadline = time.monotonic() + OBSERVATION_SECONDS
    samples = 0
    while time.monotonic() < deadline:
        booking = get_booking(client, browser, booking_id)
        samples += 1
        assert booking["status"] != "FAILED", (
            f"an unresolved payment must never be reported as a failure: {booking}"
        )
        if booking["status"] == "CONFIRMED":
            # Only reachable if Payment really captured; then exactly one ticket.
            assert len(booking["ticketIds"]) == len(seats)
            return
        assert booking["status"] in UNRESOLVED_BOOKING_STATES, booking
        assert not booking.get("ticketIds"), "no ticket before an authoritative PAID"
        # The seat stays held for this booking; the ESB does not release on a guess.
        assert seat_status(client, inventory.event_id, seats[0]) == "TAKEN"
        time.sleep(SAMPLE_INTERVAL_SECONDS)
    assert samples >= 3, "the invariant must be observed across several worker cycles"


def test_a_command_never_dispatched_releases_immediately(
    client: httpx.Client, browser: Browser, inventory: Inventory
) -> None:
    """Payment fully down: the ESB knows nothing was sent, so it compensates now."""
    seats = inventory.seat_ids[:1]
    correlation = correlation_id("pay-nodispatch")

    with service_stopped("payment"):
        # The first attempt opens the circuit; the second is rejected before dispatch.
        place_booking(client, browser, inventory, seat_ids=inventory.seat_ids[2:3])
        response = place_booking(
            client, browser, inventory, seat_ids=seats, correlation=correlation
        )

    assert response.status_code >= 400, response.text
    body = response.json()
    assert body["correlationId"] == correlation
    assert "ticketIds" not in body

    # Nothing was charged, so the seat must be free again without waiting for a TTL.
    wait_until(
        "the undispatched booking to release its seat",
        lambda: seat_status(client, inventory.event_id, seats[0]) == "AVAILABLE",
        timeout=90,
        interval=2,
    )


def test_the_esb_stays_readable_while_a_booking_is_reconciling(
    client: httpx.Client, browser: Browser, inventory: Inventory
) -> None:
    with service_paused("payment"):
        response = place_booking(
            client, browser, inventory, seat_ids=inventory.seat_ids[:1]
        )
    assert response.status_code == 202, response.text
    booking_id = response.json()["bookingId"]

    # Polling the Location target is the contract's prescribed client behaviour.
    polled = client.get(
        f"{ESB_URL}/api/bookings/{booking_id}",
        headers=browser.headers(correlation_id("poll")),
    )
    assert polled.status_code == 200, polled.text
    assert polled.json()["bookingId"] == booking_id
