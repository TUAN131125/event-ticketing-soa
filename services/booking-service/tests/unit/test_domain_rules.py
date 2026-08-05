from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.entities import Booking
from app.domain.enums import BookingStatus, PaymentStatus
from app.domain.exceptions import InvalidRequest, VersionConflict
from app.domain.rules import advisory_lock_id, canonical_request_hash
from app.domain.value_objects import BookingItem


def booking() -> Booking:
    return Booking.create(
        booking_id="BK00000001",
        customer_id="C001",
        event_id="EV001",
        items=(
            BookingItem("A-01", "VIP", Decimal("100")),
            BookingItem("A-02", "VIP", Decimal("100")),
        ),
        currency="vnd",
        now=datetime.now(UTC),
    )


def test_canonical_successful_transition_sequence() -> None:
    result = booking()
    now = datetime.now(UTC)
    result.transition(
        "bookingReservation", {"reservationId": "RES-1"}, expected_version=1, now=now
    )
    result.transition(
        "bookingPaymentStarted", {"paymentId": "PAY-1"}, expected_version=2, now=now
    )
    result.transition(
        "bookingPaymentResult",
        {"paymentId": "PAY-1", "paymentStatus": "CAPTURED"},
        expected_version=3,
        now=now,
    )
    result.transition(
        "bookingTickets", {"ticketIds": ["TKT-1"]}, expected_version=4, now=now
    )
    result.transition(
        "bookingConfirm",
        {"reservationId": "RES-1", "paymentId": "PAY-1", "ticketIds": ["TKT-1"]},
        expected_version=5,
        now=now,
    )
    assert result.status == BookingStatus.CONFIRMED
    assert result.payment_status == PaymentStatus.CAPTURED
    assert result.total_amount == Decimal("200")


def test_duplicate_seats_and_invalid_transition_are_rejected() -> None:
    with pytest.raises(InvalidRequest):
        Booking.create(
            booking_id="BK00000002",
            customer_id="C001",
            event_id="EV001",
            items=(
                BookingItem("A-01", "VIP", Decimal("100")),
                BookingItem("A-01", "VIP", Decimal("100")),
            ),
            currency="VND",
            now=datetime.now(UTC),
        )
    with pytest.raises(InvalidRequest):
        booking().transition(
            "bookingPaymentStarted",
            {"paymentId": "PAY-1"},
            expected_version=1,
            now=datetime.now(UTC),
        )


def test_expected_version_and_hash_are_deterministic() -> None:
    with pytest.raises(VersionConflict):
        booking().transition(
            "bookingReservation",
            {"reservationId": "RES-1"},
            expected_version=9,
            now=datetime.now(UTC),
        )
    assert canonical_request_hash({"b": 2, "a": 1}) == canonical_request_hash(
        {"a": 1, "b": 2}
    )
    assert advisory_lock_id("CreateBooking", "key-1") != advisory_lock_id(
        "CreateBooking", "key-2"
    )


def test_transition_evidence_timestamps_hash_canonically() -> None:
    """Transition evidence carries parsed datetimes; hashing must not raise."""
    instant = datetime(2026, 8, 5, 10, 30, tzinfo=UTC)
    payload = {"evidence": {"reservationExpiresAt": instant}}
    assert canonical_request_hash(payload) == canonical_request_hash(payload)

    # The same instant expressed in another offset is the same request.
    shifted = instant.astimezone(timezone(timedelta(hours=7)))
    assert canonical_request_hash(
        {"evidence": {"reservationExpiresAt": shifted}}
    ) == canonical_request_hash(payload)

    # A different instant is a different request.
    assert canonical_request_hash(
        {"evidence": {"reservationExpiresAt": instant + timedelta(seconds=1)}}
    ) != canonical_request_hash(payload)
