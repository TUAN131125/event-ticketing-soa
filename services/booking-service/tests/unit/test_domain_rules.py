"""Business-state tests for the refactored Booking aggregate."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.domain.entities import Booking
from app.domain.enums import (
    BookingStatus,
    CompensationAction,
    CompensationStatus,
    PaymentStatus,
    ReservationEvidenceStatus,
)
from app.domain.exceptions import (
    CompensationEvidenceRequired,
    InvalidRequest,
    InvalidStateTransition,
    MissingPaymentEvidence,
    MissingReservationEvidence,
    MissingTicketEvidence,
    VersionConflict,
)
from app.domain.rules import advisory_lock_id, canonical_request_hash
from app.domain.value_objects import BookingItem, CompensationEvidence

NOW = datetime(2026, 8, 6, 3, 0, tzinfo=UTC)
EXPIRY = NOW + timedelta(minutes=10)


def new_booking(*, legacy_reservation: bool = False) -> Booking:
    return Booking.create(
        booking_id="BK00000001",
        customer_id="C001",
        event_id="EV001",
        reservation_id="RES-001" if legacy_reservation else None,
        payment_method="CARD" if legacy_reservation else None,
        items=(
            BookingItem("A-01", "VIP", Decimal("120.00")),
            BookingItem("A-02", "VIP", Decimal("120.00")),
        ),
        total_amount=Decimal("240.00"),
        currency="VND",
        now=NOW,
    )


def reserved(*, confirmed: bool = False) -> Booking:
    booking = new_booking()
    booking.attach_reservation(
        reservation_id="RES-001",
        expected_version=booking.resource_version,
        expires_at=None if confirmed else EXPIRY,
        confirmed=confirmed,
        now=NOW,
    )
    return booking


def payment_started(*, reservation_confirmed: bool = False) -> Booking:
    booking = reserved(confirmed=reservation_confirmed)
    booking.start_payment(
        payment_id="PAY-001",
        expected_version=booking.resource_version,
        now=NOW,
    )
    return booking


def paid(*, reservation_confirmed: bool = False) -> Booking:
    booking = payment_started(reservation_confirmed=reservation_confirmed)
    booking.record_payment(
        payment_id="PAY-001",
        payment_status=PaymentStatus.SUCCEEDED,
        expected_version=booking.resource_version,
        provider_reference="PROV-001",
        now=NOW,
    )
    return booking


def confirmed_booking() -> Booking:
    booking = paid()
    booking.confirm_reservation(
        reservation_id="RES-001",
        expected_version=booking.resource_version,
        reservation_version=2,
        now=NOW,
    )
    booking.attach_tickets(
        ticket_ids=("TKT-001", "TKT-002"),
        expected_version=booking.resource_version,
        now=NOW,
    )
    booking.confirm(expected_version=booking.resource_version, now=NOW)
    return booking


def test_create_normalizes_price_snapshot_and_rejects_invalid_input() -> None:
    booking = new_booking()
    assert booking.status == BookingStatus.PENDING
    assert booking.total_amount == Decimal("240.00")
    assert booking.reservation_status == ReservationEvidenceStatus.PENDING
    assert booking.payment_status == PaymentStatus.PENDING

    with pytest.raises(InvalidRequest):
        Booking.create(
            booking_id="BK00000002",
            customer_id="C001",
            event_id="EV001",
            items=(
                BookingItem("A-01", "VIP", Decimal("100.00")),
                BookingItem("A-01", "VIP", Decimal("100.00")),
            ),
            total_amount=Decimal("200.00"),
            currency="VND",
            now=NOW,
        )
    with pytest.raises(InvalidRequest):
        Booking.create(
            booking_id="BK00000003",
            customer_id="C001",
            event_id="EV001",
            items=(BookingItem("A-01", "VIP", Decimal("100.00")),),
            total_amount=Decimal("99.00"),
            currency="VND",
            now=NOW,
        )


def test_canonical_state_machine_happy_path() -> None:
    booking = new_booking()
    booking.attach_reservation(
        reservation_id="RES-001",
        expires_at=EXPIRY,
        reservation_version=1,
        confirmed=False,
        expected_version=1,
        now=NOW,
    )
    assert booking.status == BookingStatus.SEAT_RESERVED
    assert booking.reservation_status == ReservationEvidenceStatus.RESERVED

    booking.start_payment(payment_id="PAY-001", expected_version=2, now=NOW)
    assert booking.status == BookingStatus.PAYMENT_PROCESSING
    assert booking.payment_status == PaymentStatus.PROCESSING

    booking.record_payment(
        payment_id="PAY-001",
        payment_status=PaymentStatus.SUCCEEDED,
        provider_reference="PROV-001",
        expected_version=3,
        now=NOW,
    )
    assert booking.status == BookingStatus.PAYMENT_PROCESSING
    assert booking.payment_status == PaymentStatus.SUCCEEDED

    booking.confirm_reservation(
        reservation_id="RES-001",
        reservation_version=2,
        expected_version=4,
        now=NOW,
    )
    booking.attach_tickets(
        ticket_ids=("TKT-001", "TKT-002"), expected_version=5, now=NOW
    )
    booking.confirm(expected_version=6, now=NOW)

    assert booking.status == BookingStatus.CONFIRMED
    assert booking.resource_version == 7
    assert booking.confirmed_at == NOW


def test_legacy_reservation_and_payment_inputs_remain_supported() -> None:
    booking = new_booking(legacy_reservation=True)
    booking.attach_reservation(
        reservation_id="RES-001",
        confirmed=True,
        expected_version=1,
        now=NOW,
    )
    booking.start_payment(payment_id="PAY-001", expected_version=2, now=NOW)
    booking.record_payment(
        payment_id="PAY-001", succeeded=True, expected_version=3, now=NOW
    )
    booking.attach_tickets(
        ticket_ids=("TKT-001", "TKT-002"), expected_version=4, now=NOW
    )
    booking.confirm(expected_version=5, now=NOW)
    assert booking.status == BookingStatus.CONFIRMED


def test_ordering_guards_prevent_invalid_side_effect_evidence() -> None:
    booking = new_booking()
    with pytest.raises(InvalidRequest):
        booking.start_payment(payment_id="PAY-001", expected_version=1, now=NOW)

    with pytest.raises(InvalidRequest):
        booking.attach_reservation(
            reservation_id="RES-001",
            confirmed=False,
            expected_version=1,
            now=NOW,
        )

    booking = payment_started()
    with pytest.raises(MissingPaymentEvidence):
        booking.confirm_reservation(
            reservation_id="RES-001",
            expected_version=booking.resource_version,
            now=NOW,
        )
    with pytest.raises(MissingPaymentEvidence):
        booking.attach_tickets(
            ticket_ids=("TKT-001", "TKT-002"),
            expected_version=booking.resource_version,
            now=NOW,
        )

    booking.record_payment(
        payment_id="PAY-001",
        payment_status=PaymentStatus.SUCCEEDED,
        expected_version=booking.resource_version,
        now=NOW,
    )
    with pytest.raises(MissingReservationEvidence):
        booking.attach_tickets(
            ticket_ids=("TKT-001", "TKT-002"),
            expected_version=booking.resource_version,
            now=NOW,
        )


def test_ticket_evidence_must_cover_every_booking_item() -> None:
    booking = paid(reservation_confirmed=True)
    with pytest.raises(InvalidRequest):
        booking.attach_tickets(
            ticket_ids=("TKT-001",),
            expected_version=booking.resource_version,
            now=NOW,
        )


def test_confirm_requires_all_three_authoritative_evidence_groups() -> None:
    with pytest.raises(InvalidStateTransition):
        new_booking().confirm(expected_version=1, now=NOW)

    booking = payment_started(reservation_confirmed=True)
    with pytest.raises(MissingPaymentEvidence):
        booking.confirm(expected_version=3, now=NOW)

    booking = paid(reservation_confirmed=True)
    with pytest.raises(MissingTicketEvidence):
        booking.confirm(expected_version=4, now=NOW)


def test_payment_failure_does_not_overwrite_authoritative_payment_evidence() -> None:
    booking = payment_started()
    booking.record_payment(
        payment_id="PAY-001",
        payment_status=PaymentStatus.FAILED,
        failure_code="PAYMENT_DECLINED",
        expected_version=3,
        now=NOW,
    )
    booking.fail(
        failure_code="PAYMENT_DECLINED",
        reason="provider declined payment",
        expected_version=4,
        now=NOW,
    )

    assert booking.status == BookingStatus.COMPENSATION_PENDING
    assert booking.payment_status == PaymentStatus.FAILED
    assert booking.reservation_status == ReservationEvidenceStatus.RELEASE_PENDING
    assert booking.compensation_action == CompensationAction.RELEASE_RESERVATION

    booking.record_compensation(
        expected_version=5,
        compensation_status=CompensationStatus.COMPLETED,
        evidence=CompensationEvidence(reservation_released=True, verified_at=NOW),
        now=NOW,
    )
    assert booking.status == BookingStatus.FAILED
    assert booking.payment_status == PaymentStatus.FAILED
    assert booking.reservation_status == ReservationEvidenceStatus.RELEASED


def test_unknown_payment_is_reconciled_before_release_or_refund_decision() -> None:
    booking = payment_started()
    booking.record_payment(
        payment_id="PAY-001",
        payment_status=PaymentStatus.UNKNOWN,
        expected_version=3,
        now=NOW,
    )
    booking.fail(
        failure_code="PAYMENT_UNKNOWN",
        reason="provider response was lost",
        expected_version=4,
        now=NOW,
    )
    assert booking.status == BookingStatus.COMPENSATION_PENDING
    assert booking.compensation_action == CompensationAction.RECONCILE_PAYMENT
    assert booking.payment_status == PaymentStatus.UNKNOWN

    booking.record_payment(
        payment_id="PAY-001",
        payment_status=PaymentStatus.FAILED,
        expected_version=5,
        now=NOW,
    )
    assert booking.compensation_action == CompensationAction.RELEASE_RESERVATION
    assert booking.reservation_status == ReservationEvidenceStatus.RELEASE_PENDING

    booking.record_compensation(
        expected_version=6,
        compensation_status=CompensationStatus.COMPLETED,
        evidence=CompensationEvidence(reservation_released=True),
        now=NOW,
    )
    assert booking.status == BookingStatus.FAILED


def test_successful_payment_failure_requires_release_and_refund_evidence() -> None:
    booking = paid(reservation_confirmed=True)
    booking.fail(
        failure_code="TICKET_ISSUE_FAILED",
        reason="ticket service failed after payment",
        expected_version=4,
        now=NOW,
    )
    assert booking.status == BookingStatus.COMPENSATION_PENDING
    assert booking.compensation_action == CompensationAction.RELEASE_AND_REFUND
    assert booking.payment_status == PaymentStatus.REFUND_PENDING
    assert booking.reservation_status == ReservationEvidenceStatus.RELEASE_PENDING

    with pytest.raises(CompensationEvidenceRequired):
        booking.record_compensation(
            expected_version=5,
            compensation_status=CompensationStatus.COMPLETED,
            evidence=CompensationEvidence(reservation_released=True),
            now=NOW,
        )

    # The failed transaction above does not roll back an in-memory aggregate,
    # so recreate the state to assert the complete evidence path.
    booking = paid(reservation_confirmed=True)
    booking.fail(
        failure_code="TICKET_ISSUE_FAILED",
        reason="ticket service failed after payment",
        expected_version=4,
        now=NOW,
    )
    booking.record_compensation(
        expected_version=5,
        compensation_status=CompensationStatus.COMPLETED,
        evidence=CompensationEvidence(
            reservation_released=True,
            payment_refunded=True,
            provider_reference="REF-001",
        ),
        now=NOW,
    )
    assert booking.status == BookingStatus.FAILED
    assert booking.payment_status == PaymentStatus.REFUNDED
    assert booking.reservation_status == ReservationEvidenceStatus.RELEASED


def test_cancel_confirmed_booking_waits_for_release_and_refund() -> None:
    booking = confirmed_booking()
    booking.cancel(
        reason="customer requested cancellation",
        expected_version=booking.resource_version,
        now=NOW,
    )
    assert booking.status == BookingStatus.COMPENSATION_PENDING
    assert booking.intended_terminal_status == BookingStatus.CANCELLED
    assert booking.compensation_action == CompensationAction.RELEASE_AND_REFUND

    booking.record_compensation(
        expected_version=booking.resource_version,
        compensation_status=CompensationStatus.COMPLETED,
        evidence=CompensationEvidence(
            reservation_released=True, payment_refunded=True
        ),
        now=NOW,
    )
    assert booking.status == BookingStatus.CANCELLED
    assert booking.cancelled_at == NOW


def test_pending_booking_can_fail_or_cancel_without_fabricated_compensation() -> None:
    failed = new_booking()
    failed.fail(
        failure_code="EVENT_NOT_ON_SALE",
        reason="event is not on sale",
        expected_version=1,
        now=NOW,
    )
    assert failed.status == BookingStatus.FAILED
    assert failed.compensation_status == CompensationStatus.NOT_REQUIRED

    cancelled = new_booking()
    cancelled.cancel(reason="customer stopped checkout", expected_version=1, now=NOW)
    assert cancelled.status == BookingStatus.CANCELLED
    assert cancelled.compensation_status == CompensationStatus.NOT_REQUIRED


def test_terminal_state_and_version_guards() -> None:
    booking = confirmed_booking()
    with pytest.raises(InvalidRequest):
        booking.fail(
            failure_code="LATE_FAILURE",
            reason="not allowed",
            expected_version=booking.resource_version,
            now=NOW,
        )
    with pytest.raises(VersionConflict):
        booking.cancel(reason="stale", expected_version=1, now=NOW)


def test_hash_and_lock_are_deterministic() -> None:
    assert canonical_request_hash({"b": 2, "a": 1}) == canonical_request_hash(
        {"a": 1, "b": 2}
    )
    assert canonical_request_hash({"amount": Decimal("1.0")}) == canonical_request_hash(
        {"amount": Decimal("1.00")}
    )
    assert advisory_lock_id("CreateBooking", "key-1") == advisory_lock_id(
        "CreateBooking", "key-1"
    )
    assert advisory_lock_id("CreateBooking", "key-1") != advisory_lock_id(
        "CreateBooking", "key-2"
    )
