"""Two browsers racing for one seat: exactly one booking may win."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import httpx

from tests.support.e2e import (
    REQUEST_TIMEOUT,
    Browser,
    Inventory,
    correlation_id,
    place_booking,
    seat_status,
)


def test_concurrent_requests_for_one_seat_produce_exactly_one_confirmed_booking(
    client: httpx.Client,
    browser: Browser,
    other_browser: Browser,
    inventory: Inventory,
) -> None:
    contested = inventory.seat_ids[:1]

    def attempt(user: Browser) -> httpx.Response:
        with httpx.Client(timeout=REQUEST_TIMEOUT) as isolated:
            return place_booking(
                isolated,
                user,
                inventory,
                seat_ids=contested,
                correlation=correlation_id("race"),
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(attempt, (browser, other_browser)))

    confirmed = [
        response
        for response in responses
        if response.status_code == 201 and response.json()["status"] == "CONFIRMED"
    ]
    rejected = [response for response in responses if response.status_code != 201]

    assert len(confirmed) == 1, (
        "exactly one booking may own a seat; got "
        f"{[(response.status_code, response.text) for response in responses]}"
    )
    assert len(rejected) == 1
    assert rejected[0].status_code == 409, rejected[0].text
    assert rejected[0].json()["error"]["code"] in {"OUT_OF_STOCK", "SEAT_UNAVAILABLE"}
    assert rejected[0].json()["error"]["retryable"] is False

    assert seat_status(client, inventory.event_id, contested[0]) == "TAKEN"


def test_a_sold_seat_cannot_be_booked_again(
    client: httpx.Client,
    browser: Browser,
    other_browser: Browser,
    inventory: Inventory,
) -> None:
    seat = inventory.seat_ids[:1]
    first = place_booking(client, browser, inventory, seat_ids=seat)
    assert first.status_code == 201, first.text

    second = place_booking(client, other_browser, inventory, seat_ids=seat)
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] in {"OUT_OF_STOCK", "SEAT_UNAVAILABLE"}
