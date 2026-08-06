"""Command compatibility, idempotency hashes and evidence validation."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.application.commands.attach_reservation import AttachReservation
from app.application.commands.cancel_booking import CancelBooking
from app.application.commands.confirm_booking import ConfirmBooking
from app.application.commands.confirm_reservation import ConfirmReservation
from app.application.commands.fail_booking import FailBooking
from app.application.commands.record_payment import RecordPayment
from app.domain.entities import Booking
from app.domain.enums import (
    CompensationStatus,
    PaymentStatus,
    ReservationEvidenceStatus,
)
from app.domain.exceptions import InvalidRequest
from app.domain.value_objects import BookingItem, CompensationEvidence

NOW = datetime(2026, 8, 6, 3, 0, tzinfo=UTC)


def booking() -> Booking:
    return Booking.create(
        booking_id="BK00000001",
        customer_id="C001",
        event_id="EV001",
        items=(BookingItem("A-01", "VIP", Decimal("100.00")),),
        currency="VND",
        total_amount=Decimal("100.00"),
        now=NOW,
    )


def test_legacy_command_hash_payloads_are_preserved() -> None:
    assert AttachReservation.of(
        booking_id="BK00000001", reservation_id="RES-001", expected_version=1
    ).request_payload() == {
        "bookingId": "BK00000001",
        "reservationId": "RES-001",
        "expectedVersion": 1,
    }
    assert RecordPayment.of(
        booking_id="BK00000001",
        payment_id="PAY-001",
        succeeded=True,
        expected_version=3,
    ).request_payload() == {
        "bookingId": "BK00000001",
        "paymentId": "PAY-001",
        "succeeded": True,
        "expectedVersion": 3,
    }
    assert ConfirmBooking.of(
        booking_id="BK00000001", expected_version=5
    ).request_payload() == {
        "bookingId": "BK00000001",
        "expectedVersion": 5,
    }
    assert FailBooking.of(
        booking_id="BK00000001",
        failure_code="SEAT_LOST",
        reason="seat lost",
        expected_version=2,
    ).request_payload() == {
        "bookingId": "BK00000001",
        "failureCode": "SEAT_LOST",
        "reason": "seat lost",
        "expectedVersion": 2,
    }
    assert CancelBooking.of(
        booking_id="BK00000001",
        reason="customer request",
        expected_version=2,
    ).request_payload() == {
        "bookingId": "BK00000001",
        "reason": "customer request",
        "expectedVersion": 2,
        "paymentStatus": None,
    }


def test_new_command_payloads_include_only_new_evidence_when_used() -> None:
    expiry = NOW + timedelta(minutes=5)
    payload = AttachReservation.of(
        booking_id="BK00000001",
        reservation_id="RES-001",
        expected_version=1,
        expires_at=expiry,
        reservation_version=4,
        confirmed=False,
    ).request_payload()
    assert payload["reservationExpiresAt"] == expiry.isoformat()
    assert payload["confirmed"] is False

    payment = RecordPayment.of(
        booking_id="BK00000001",
        payment_id="PAY-001",
        payment_status=PaymentStatus.UNKNOWN,
        provider_reference="PROV-001",
        expected_version=3,
    ).request_payload()
    assert payment["paymentStatus"] == "UNKNOWN"
    assert "succeeded" not in payment

    confirmation = ConfirmBooking.of(
        booking_id="BK00000001",
        expected_version=6,
        reservation_id="RES-001",
        payment_id="PAY-001",
        payment_status=PaymentStatus.SUCCEEDED,
        ticket_ids=("TKT-001",),
        seat_confirmed=True,
        payment_captured=True,
        tickets_issued=True,
    ).request_payload()
    assert confirmation["seatConfirmed"] is True
    assert confirmation["ticketIds"] == ["TKT-001"]


def test_confirm_command_rejects_mismatched_supplied_evidence() -> None:
    aggregate = booking()
    aggregate.attach_reservation(
        reservation_id="RES-001", confirmed=True, expected_version=1, now=NOW
    )
    aggregate.start_payment(payment_id="PAY-001", expected_version=2, now=NOW)
    aggregate.record_payment(
        payment_id="PAY-001", succeeded=True, expected_version=3, now=NOW
    )
    aggregate.attach_tickets(
        ticket_ids=("TKT-001",), expected_version=4, now=NOW
    )

    command = ConfirmBooking.of(
        booking_id=aggregate.booking_id,
        expected_version=5,
        payment_id="PAY-OTHER",
    )
    with pytest.raises(InvalidRequest):
        command.apply(aggregate, NOW)


def test_failure_and_cancel_payloads_include_compensation_evidence() -> None:
    evidence = CompensationEvidence(
        reservation_released=True,
        payment_refunded=True,
        provider_reference="REF-001",
        resolved_payment_status=PaymentStatus.REFUNDED,
    )
    failed = FailBooking.of(
        booking_id="BK00000001",
        failure_code="PAYMENT_UNKNOWN",
        reason="reconciled",
        expected_version=4,
        compensation_status=CompensationStatus.COMPLETED,
        evidence=evidence,
    ).request_payload()
    assert failed["resolvedPaymentStatus"] == "REFUNDED"
    assert failed["reservationReleased"] is True

    cancelled = CancelBooking.of(
        booking_id="BK00000001",
        reason="cancelled",
        expected_version=4,
        compensation_status=CompensationStatus.COMPLETED,
        evidence=evidence,
    ).request_payload()
    assert cancelled["paymentRefunded"] is True


def test_attach_reservation_lost_key_replay_checks_evidence() -> None:
    aggregate = booking()
    command = AttachReservation.of(
        booking_id=aggregate.booking_id,
        reservation_id="RES-001",
        expected_version=1,
        confirmed=True,
    )
    assert command.is_already_applied(aggregate) is False
    command.apply(aggregate, NOW)
    assert aggregate.reservation_status == ReservationEvidenceStatus.CONFIRMED
    assert command.is_already_applied(aggregate) is True

    other = AttachReservation.of(
        booking_id=aggregate.booking_id,
        reservation_id="RES-OTHER",
        expected_version=1,
        confirmed=True,
    )
    with pytest.raises(InvalidRequest):
        other.is_already_applied(aggregate)


def test_reservation_replays_accept_evidence_that_has_safely_advanced() -> None:
    aggregate = booking()
    expires_at = NOW + timedelta(minutes=10)
    attach = AttachReservation.of(
        booking_id=aggregate.booking_id,
        reservation_id="RES-001",
        expected_version=1,
        expires_at=expires_at,
        reservation_version=1,
        confirmed=False,
    )
    attach.apply(aggregate, NOW)
    aggregate.start_payment(
        payment_id="PAY-001", expected_version=2, now=NOW
    )
    aggregate.record_payment(
        payment_id="PAY-001", succeeded=True, expected_version=3, now=NOW
    )
    aggregate.confirm_reservation(
        reservation_id="RES-001",
        reservation_version=2,
        expected_version=4,
        now=NOW,
    )

    assert attach.is_already_applied(aggregate) is True
    confirmation = ConfirmReservation.of(
        booking_id=aggregate.booking_id,
        reservation_id="RES-001",
        expected_version=4,
        reservation_version=1,
    )
    assert confirmation.is_already_applied(aggregate) is True


def test_payment_still_processing_requires_reconciliation_before_failure() -> None:
    aggregate = booking()
    aggregate.attach_reservation(
        reservation_id="RES-001",
        expires_at=NOW + timedelta(minutes=10),
        expected_version=1,
        now=NOW,
    )
    aggregate.start_payment(
        payment_id="PAY-001", expected_version=2, now=NOW
    )
    aggregate.fail(
        failure_code="PAYMENT_TIMEOUT",
        reason="payment response was not observed",
        expected_version=3,
        now=NOW,
    )

    assert aggregate.status.value == "COMPENSATION_PENDING"
    assert aggregate.compensation_action.value == "RECONCILE_PAYMENT"
    assert aggregate.payment_status == PaymentStatus.PROCESSING
