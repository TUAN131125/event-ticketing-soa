"""HTTP concurrency compatibility tests."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi import Response

from app.api.v1.http_contract import booking_response, resolve_expected_version
from app.domain.entities import Booking
from app.domain.exceptions import InvalidRequest
from app.domain.value_objects import BookingItem

NOW = datetime(2026, 8, 6, 3, 0, tzinfo=UTC)


def test_resolve_expected_version_accepts_legacy_body_only() -> None:
    assert resolve_expected_version(4, None) == 4


def test_resolve_expected_version_accepts_strong_and_weak_etags() -> None:
    assert resolve_expected_version(None, '"4"') == 4
    assert resolve_expected_version(None, 'W/"4"') == 4


def test_resolve_expected_version_accepts_matching_forms() -> None:
    assert resolve_expected_version(4, '"4"') == 4


@pytest.mark.parametrize(
    ("body_version", "if_match"),
    [
        (4, '"5"'),
        (None, None),
        (None, "not-an-etag"),
        (None, '"0"'),
    ],
)
def test_resolve_expected_version_rejects_invalid_contracts(
    body_version: int | None,
    if_match: str | None,
) -> None:
    with pytest.raises(InvalidRequest):
        resolve_expected_version(body_version, if_match)


def test_booking_response_sets_entity_tag() -> None:
    booking = Booking.create(
        booking_id="BK00000001",
        customer_id="C001",
        event_id="EV001",
        items=(BookingItem("A-01", "VIP", Decimal("120")),),
        total_amount=Decimal("120"),
        currency="VND",
        now=NOW,
    )
    response = Response()

    payload = booking_response(booking, response)

    assert response.headers["ETag"] == '"1"'
    assert payload.resource_version == 1
