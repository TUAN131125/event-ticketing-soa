"""Idempotency snapshots must round-trip every aggregate state exactly."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.application.common import booking_from_payload, booking_to_payload
from app.domain.entities import Booking
from app.domain.enums import CompensationStatus, PaymentStatus
from app.domain.value_objects import BookingItem, CompensationEvidence
from app.schemas.responses import BookingResponse

NOW = datetime(2026, 8, 6, 3, 0, tzinfo=UTC)


def pending() -> Booking:
    return Booking.create(
        booking_id="BK00000001",
        customer_id="C001",
        event_id="EV001",
        items=(
            BookingItem("A-01", "VIP", Decimal("120.00")),
            BookingItem("A-02", "VIP", Decimal("120.00")),
        ),
        total_amount=Decimal("240.00"),
        currency="VND",
        now=NOW,
    )


def confirmed() -> Booking:
    booking = pending()
    booking.attach_reservation(
        reservation_id="RES-1",
        expires_at=NOW + timedelta(minutes=10),
        expected_version=1,
        now=NOW,
    )
    booking.start_payment(payment_id="PAY-1", expected_version=2, now=NOW)
    booking.record_payment(
        payment_id="PAY-1", succeeded=True, expected_version=3, now=NOW
    )
    booking.confirm_reservation(
        reservation_id="RES-1", expected_version=4, now=NOW
    )
    booking.attach_tickets(
        ticket_ids=("TKT-1", "TKT-2"), expected_version=5, now=NOW
    )
    booking.confirm(expected_version=6, now=NOW)
    return booking


def failed() -> Booking:
    booking = pending()
    booking.fail(
        failure_code="EVENT_NOT_ON_SALE",
        reason="event closed",
        expected_version=1,
        now=NOW,
    )
    return booking


def compensation_pending() -> Booking:
    booking = pending()
    booking.attach_reservation(
        reservation_id="RES-1", confirmed=True, expected_version=1, now=NOW
    )
    booking.start_payment(payment_id="PAY-1", expected_version=2, now=NOW)
    booking.record_payment(
        payment_id="PAY-1", succeeded=True, expected_version=3, now=NOW
    )
    booking.fail(
        failure_code="TICKET_ISSUE_FAILED",
        reason="ticket service unavailable",
        expected_version=4,
        now=NOW,
    )
    return booking


def cancelled() -> Booking:
    booking = confirmed()
    booking.cancel(reason="customer request", expected_version=7, now=NOW)
    booking.record_compensation(
        expected_version=8,
        compensation_status=CompensationStatus.COMPLETED,
        evidence=CompensationEvidence(
            reservation_released=True, payment_refunded=True
        ),
        now=NOW,
    )
    return booking


@pytest.mark.parametrize(
    "booking",
    [pending(), confirmed(), failed(), compensation_pending(), cancelled()],
    ids=["pending", "confirmed", "failed", "compensation", "cancelled"],
)
def test_replay_snapshot_round_trips_whole_aggregate(booking: Booking) -> None:
    replayed = booking_from_payload(booking_to_payload(booking))
    assert replayed == booking
    assert BookingResponse.from_entity(replayed).model_dump(by_alias=True) == (
        BookingResponse.from_entity(booking).model_dump(by_alias=True)
    )
