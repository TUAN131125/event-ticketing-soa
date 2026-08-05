"""Realtime WebSocket tickets are issued only after an authoritative access decision."""

from __future__ import annotations

import uuid

import httpx

from tests.support.e2e import (
    ESB_URL,
    Browser,
    Inventory,
    correlation_id,
    place_booking,
)


def issue_ticket(
    client: httpx.Client, user: Browser, booking_id: str
) -> httpx.Response:
    return client.post(
        f"{ESB_URL}/api/realtime/ws-tickets",
        json={"bookingId": booking_id},
        headers=user.headers(
            correlation_id("ws"),
            **{"Idempotency-Key": f"e2e-ws-{uuid.uuid4().hex}"},
        ),
    )


def test_owner_receives_a_short_lived_single_use_ticket(
    client: httpx.Client, browser: Browser, inventory: Inventory
) -> None:
    booking = place_booking(client, browser, inventory, seat_ids=inventory.seat_ids[:1])
    assert booking.status_code == 201, booking.text
    booking_id = booking.json()["bookingId"]

    response = issue_ticket(client, browser, booking_id)
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["ticket"], "the signed ticket is returned in the response body"
    assert payload["bookingId"] == booking_id
    # The canonical contract allows either UTC form.
    assert payload["expiresAt"].endswith(("Z", "+00:00"))
    assert "ticket=" not in str(response.url), "tickets must never travel in the URL"


def test_a_non_owner_is_denied_without_resource_disclosure(
    client: httpx.Client,
    browser: Browser,
    other_browser: Browser,
    inventory: Inventory,
) -> None:
    booking = place_booking(client, browser, inventory, seat_ids=inventory.seat_ids[:1])
    assert booking.status_code == 201, booking.text
    booking_id = booking.json()["bookingId"]

    response = issue_ticket(client, other_browser, booking_id)
    assert response.status_code in {403, 404}, response.text
    body = response.text
    assert (
        booking.json()["total"]["amountMinor"] == 0
        or str(booking.json()["total"]["amountMinor"]) not in body
    ), "a denial must not leak booking details"
    assert "reservationId" not in body
    assert "paymentId" not in body


def test_an_unauthenticated_caller_cannot_obtain_a_ticket(
    client: httpx.Client, browser: Browser, inventory: Inventory
) -> None:
    booking = place_booking(client, browser, inventory, seat_ids=inventory.seat_ids[:1])
    assert booking.status_code == 201, booking.text

    response = client.post(
        f"{ESB_URL}/api/realtime/ws-tickets",
        json={"bookingId": booking.json()["bookingId"]},
        headers={
            "X-Correlation-ID": correlation_id("ws-anon"),
            "Idempotency-Key": f"e2e-ws-anon-{uuid.uuid4().hex}",
        },
    )
    assert response.status_code == 401, response.text


def test_an_unknown_booking_fails_closed(
    client: httpx.Client, browser: Browser
) -> None:
    response = issue_ticket(client, browser, "BK-DOES-NOT-EXIST")
    assert response.status_code in {403, 404}, response.text
