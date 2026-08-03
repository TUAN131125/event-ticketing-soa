from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.domain.entities import Booking
from app.domain.enums import BookingStatus, PaymentStatus
from app.domain.exceptions import (
    InvalidRequest,
    InvalidStateTransition,
    VersionConflict,
)
from app.domain.rules import advisory_lock_id, canonical_request_hash
from app.domain.value_objects import BookingItem


def booking() -> Booking:
    return Booking.create(
        booking_id="BK00000001",
        customer_id="C001",
        event_id="EV001",
        reservation_id="RES-001",
        payment_method="CARD",
        items=(
            BookingItem("A-01", "VIP", Decimal("100.00")),
            BookingItem("A-02", "VIP", Decimal("100.00")),
        ),
        total_amount=Decimal("200.00"),
        currency="vnd",
        now=datetime.now(UTC),
    )


def test_create_normalizes_items_currency_and_total() -> None:
    result = booking()
    assert result.currency == "VND"
    assert [item.seat_id for item in result.items] == ["A-01", "A-02"]
    assert result.status == BookingStatus.PENDING
    assert result.payment_status == PaymentStatus.PENDING


def test_duplicate_seats_and_wrong_total_are_rejected() -> None:
    with pytest.raises(InvalidRequest):
        Booking.create(
            booking_id="BK00000001",
            customer_id="C001",
            event_id="EV001",
            reservation_id="RES-001",
            payment_method="CARD",
            items=(
                BookingItem("A-01", "VIP", Decimal("100")),
                BookingItem("A-01", "VIP", Decimal("100")),
            ),
            total_amount=Decimal("200"),
            currency="VND",
            now=datetime.now(UTC),
        )
    with pytest.raises(InvalidRequest):
        Booking.create(
            booking_id="BK00000002",
            customer_id="C001",
            event_id="EV001",
            reservation_id="RES-002",
            payment_method="CARD",
            items=(BookingItem("A-01", "VIP", Decimal("100")),),
            total_amount=Decimal("99"),
            currency="VND",
            now=datetime.now(UTC),
        )


def test_domain_rejects_values_that_do_not_fit_persistence_contract() -> None:
    with pytest.raises(InvalidRequest):
        Booking.create(
            booking_id="BK00000002",
            customer_id="C001",
            event_id="EV001",
            reservation_id="RES-002",
            payment_method="C" * 41,
            items=(BookingItem("A-01", "VIP", Decimal("10.001")),),
            total_amount=Decimal("10.001"),
            currency="VND",
            now=datetime.now(UTC),
        )

    with pytest.raises(InvalidRequest):
        Booking.create(
            booking_id="BK00000003",
            customer_id="C001",
            event_id="EV001",
            reservation_id="RES-003",
            payment_method="CARD",
            items=(BookingItem("A-01", "VIP", Decimal("10000000000000000")),),
            total_amount=Decimal("10000000000000000"),
            currency="VND",
            now=datetime.now(UTC),
        )


def test_confirm_then_cancel_requires_refund() -> None:
    result = booking()
    now = datetime.now(UTC)
    result.confirm(payment_id="PAY-1", expected_version=1, now=now)
    assert result.status == BookingStatus.CONFIRMED
    assert result.resource_version == 2
    with pytest.raises(InvalidRequest):
        result.cancel(
            reason="customer request",
            expected_version=2,
            payment_status=None,
            now=now,
        )
    result.cancel(
        reason="customer request",
        expected_version=2,
        payment_status=PaymentStatus.REFUNDED,
        now=now,
    )
    assert result.status == BookingStatus.CANCELLED
    assert result.payment_status == PaymentStatus.REFUNDED


def test_failed_and_cancelled_bookings_are_terminal() -> None:
    failed = booking()
    failed.fail(
        failure_code="PAYMENT_DECLINED",
        reason="The issuer declined payment",
        expected_version=1,
        now=datetime.now(UTC),
    )
    with pytest.raises(InvalidStateTransition):
        failed.confirm(payment_id="PAY-2", expected_version=2, now=datetime.now(UTC))


def test_expected_version_is_enforced() -> None:
    with pytest.raises(VersionConflict):
        booking().confirm(payment_id="PAY-1", expected_version=9, now=datetime.now(UTC))


def test_hash_and_lock_are_deterministic() -> None:
    assert canonical_request_hash({"b": 2, "a": 1}) == canonical_request_hash(
        {"a": 1, "b": 2}
    )
    assert advisory_lock_id("CreateBooking", "key-1") == advisory_lock_id(
        "CreateBooking", "key-1"
    )
    assert advisory_lock_id("CreateBooking", "key-1") != advisory_lock_id(
        "CreateBooking", "key-2"
    )
    assert canonical_request_hash({"amount": Decimal("1.0")}) == (
        canonical_request_hash({"amount": Decimal("1.00")})
    )
