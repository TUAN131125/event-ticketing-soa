"""PostgreSQL integration tests for Booking aggregate invariants."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.application.service import BookingService
from app.domain.enums import (
    BookingStatus,
    CompensationAction,
    CompensationStatus,
    PaymentStatus,
    ReservationEvidenceStatus,
)
from app.domain.exceptions import (
    IdempotencyConflict,
    InvalidRequest,
    MissingPaymentEvidence,
    MissingReservationEvidence,
    ReservationConflict,
)
from app.domain.value_objects import BookingItem, CompensationEvidence, RequestContext
from app.infrastructure.database.models import BookingAuditModel, OutboxEventModel

pytestmark = pytest.mark.integration


def context(value: str = "COR-1") -> RequestContext:
    return RequestContext(value, "booking-orchestrator", "USER-1")


def create(
    service: BookingService,
    *,
    key: str = "CREATE-1",
    customer_id: str = "C001",
    reservation_id: str | None = None,
):
    return service.create(
        context(),
        idempotency_key=key,
        customer_id=customer_id,
        event_id="EV001",
        reservation_id=reservation_id,
        payment_method="CARD" if reservation_id else None,
        items=(
            BookingItem("A-01", "VIP", Decimal("120.00")),
            BookingItem("A-02", "VIP", Decimal("120.00")),
        ),
        total_amount=Decimal("240.00"),
        currency="VND",
    )


def counts(service: BookingService) -> tuple[int, int]:
    with service.session_factory() as session:
        return (
            int(
                session.scalar(select(func.count()).select_from(BookingAuditModel)) or 0
            ),
            int(
                session.scalar(select(func.count()).select_from(OutboxEventModel)) or 0
            ),
        )


def attach_hold(
    service: BookingService,
    booking_id: str,
    version: int,
    *,
    reservation_id: str = "RES-1",
    key: str = "ATTACH-RESERVATION",
):
    return service.attach_reservation(
        context("COR-RESERVE"),
        idempotency_key=key,
        booking_id=booking_id,
        reservation_id=reservation_id,
        expires_at=datetime.now(UTC) + timedelta(minutes=10),
        reservation_version=1,
        confirmed=False,
        expected_version=version,
    )


def successful_evidence(
    service: BookingService,
    booking_id: str,
    version: int,
    *,
    prefix: str = "FLOW",
    reservation_id: str = "RES-1",
    payment_id: str = "PAY-1",
):
    reserved = attach_hold(
        service,
        booking_id,
        version,
        reservation_id=reservation_id,
        key=f"{prefix}-reservation",
    )
    started = service.start_payment(
        context("COR-PAYMENT-START"),
        idempotency_key=f"{prefix}-payment-start",
        booking_id=booking_id,
        payment_id=payment_id,
        expected_version=reserved.resource_version,
    )
    paid = service.record_payment(
        context("COR-PAYMENT-RESULT"),
        idempotency_key=f"{prefix}-payment-result",
        booking_id=booking_id,
        payment_id=payment_id,
        payment_status=PaymentStatus.SUCCEEDED,
        provider_reference=f"PROVIDER-{prefix}",
        expected_version=started.resource_version,
    )
    seat_confirmed = service.confirm_reservation(
        context("COR-SEAT-CONFIRM"),
        idempotency_key=f"{prefix}-seat-confirm",
        booking_id=booking_id,
        reservation_id=reservation_id,
        reservation_version=2,
        expected_version=paid.resource_version,
    )
    return service.attach_tickets(
        context("COR-TICKETS"),
        idempotency_key=f"{prefix}-tickets",
        booking_id=booking_id,
        ticket_ids=(f"TKT-{prefix}-1", f"TKT-{prefix}-2"),
        expected_version=seat_confirmed.resource_version,
    )


def confirm_booking(
    service: BookingService,
    booking_id: str,
    version: int,
    *,
    key: str,
):
    return service.confirm(
        context("COR-CONFIRM"),
        idempotency_key=key,
        booking_id=booking_id,
        expected_version=version,
    )


def test_canonical_lifecycle_is_persistent_audited_and_idempotent(
    service: BookingService,
) -> None:
    original = create(service)
    replay = create(service)
    assert replay.booking_id == original.booking_id
    assert counts(service) == (1, 1)

    ticketed = successful_evidence(
        service, original.booking_id, original.resource_version
    )
    assert ticketed.status == BookingStatus.PAYMENT_PROCESSING
    assert ticketed.reservation_status == ReservationEvidenceStatus.CONFIRMED
    assert ticketed.payment_status == PaymentStatus.SUCCEEDED
    assert len(ticketed.ticket_ids) == 2
    assert counts(service) == (6, 1)

    confirmed = confirm_booking(
        service,
        original.booking_id,
        ticketed.resource_version,
        key="CONFIRM-1",
    )
    assert confirmed.status == BookingStatus.CONFIRMED
    assert counts(service) == (7, 2)

    lost_key_retry = confirm_booking(
        service,
        original.booking_id,
        ticketed.resource_version,
        key="CONFIRM-LOST-KEY",
    )
    assert lost_key_retry.resource_version == confirmed.resource_version
    assert counts(service) == (7, 2)

    history = service.history(original.booking_id)
    assert [entry.operation for entry in history] == [
        "CreateBooking",
        "AttachReservation",
        "StartPayment",
        "RecordPayment",
        "ConfirmReservation",
        "AttachTickets",
        "ConfirmBooking",
    ]


def test_confirmed_cancellation_waits_for_release_and_refund_evidence(
    service: BookingService,
) -> None:
    booking = create(service, key="CREATE-CANCEL")
    ticketed = successful_evidence(
        service,
        booking.booking_id,
        booking.resource_version,
        prefix="CANCEL",
        reservation_id="RES-CANCEL",
        payment_id="PAY-CANCEL",
    )
    confirmed = confirm_booking(
        service,
        booking.booking_id,
        ticketed.resource_version,
        key="CONFIRM-CANCEL",
    )

    pending = service.cancel(
        context("COR-CANCEL"),
        idempotency_key="CANCEL-1",
        booking_id=booking.booking_id,
        reason="customer requested cancellation",
        expected_version=confirmed.resource_version,
    )
    assert pending.status == BookingStatus.COMPENSATION_PENDING
    assert pending.intended_terminal_status == BookingStatus.CANCELLED
    assert pending.compensation_action == CompensationAction.RELEASE_AND_REFUND
    assert pending.reservation_status == ReservationEvidenceStatus.RELEASE_PENDING
    assert pending.payment_status == PaymentStatus.REFUND_PENDING

    cancelled = service.record_compensation(
        context("COR-COMPENSATE"),
        idempotency_key="COMPENSATE-CANCEL-1",
        booking_id=booking.booking_id,
        expected_version=pending.resource_version,
        compensation_status=CompensationStatus.COMPLETED,
        evidence=CompensationEvidence(
            reservation_released=True,
            payment_refunded=True,
            provider_reference="REF-CANCEL-1",
            verified_at=datetime.now(UTC),
        ),
        reason="seat released and payment refunded",
    )
    assert cancelled.status == BookingStatus.CANCELLED
    assert cancelled.compensation_status == CompensationStatus.COMPLETED
    assert cancelled.reservation_status == ReservationEvidenceStatus.RELEASED
    assert cancelled.payment_status == PaymentStatus.REFUNDED
    assert cancelled.cancelled_at is not None


def test_payment_decline_fails_only_after_seat_release_evidence(
    service: BookingService,
) -> None:
    booking = create(service, key="CREATE-DECLINE")
    reserved = attach_hold(
        service,
        booking.booking_id,
        booking.resource_version,
        reservation_id="RES-DECLINE",
        key="RESERVE-DECLINE",
    )
    started = service.start_payment(
        context(),
        idempotency_key="START-DECLINE",
        booking_id=booking.booking_id,
        payment_id="PAY-DECLINE",
        expected_version=reserved.resource_version,
    )
    declined = service.record_payment(
        context(),
        idempotency_key="RECORD-DECLINE",
        booking_id=booking.booking_id,
        payment_id="PAY-DECLINE",
        payment_status=PaymentStatus.FAILED,
        failure_code="PAYMENT_DECLINED",
        expected_version=started.resource_version,
    )
    pending = service.fail(
        context(),
        idempotency_key="FAIL-DECLINE",
        booking_id=booking.booking_id,
        failure_code="PAYMENT_DECLINED",
        reason="provider declined payment",
        expected_version=declined.resource_version,
    )
    assert pending.status == BookingStatus.COMPENSATION_PENDING
    assert pending.compensation_action == CompensationAction.RELEASE_RESERVATION
    assert pending.payment_status == PaymentStatus.FAILED

    failed = service.record_compensation(
        context(),
        idempotency_key="RELEASE-DECLINE",
        booking_id=booking.booking_id,
        expected_version=pending.resource_version,
        compensation_status=CompensationStatus.COMPLETED,
        evidence=CompensationEvidence(
            reservation_released=True,
            verified_at=datetime.now(UTC),
        ),
    )
    assert failed.status == BookingStatus.FAILED
    assert failed.payment_status == PaymentStatus.FAILED
    assert failed.reservation_status == ReservationEvidenceStatus.RELEASED


def test_unknown_payment_is_reconciled_before_compensation_is_chosen(
    service: BookingService,
) -> None:
    booking = create(service, key="CREATE-UNKNOWN")
    reserved = attach_hold(
        service,
        booking.booking_id,
        booking.resource_version,
        reservation_id="RES-UNKNOWN",
        key="RESERVE-UNKNOWN",
    )
    started = service.start_payment(
        context(),
        idempotency_key="START-UNKNOWN",
        booking_id=booking.booking_id,
        payment_id="PAY-UNKNOWN",
        expected_version=reserved.resource_version,
    )
    unknown = service.record_payment(
        context(),
        idempotency_key="RECORD-UNKNOWN",
        booking_id=booking.booking_id,
        payment_id="PAY-UNKNOWN",
        payment_status=PaymentStatus.UNKNOWN,
        expected_version=started.resource_version,
    )
    pending = service.fail(
        context(),
        idempotency_key="FAIL-UNKNOWN",
        booking_id=booking.booking_id,
        failure_code="PAYMENT_UNKNOWN",
        reason="provider response was lost",
        expected_version=unknown.resource_version,
    )
    assert pending.compensation_action == CompensationAction.RECONCILE_PAYMENT

    resolved = service.record_payment(
        context(),
        idempotency_key="RECONCILE-UNKNOWN",
        booking_id=booking.booking_id,
        payment_id="PAY-UNKNOWN",
        payment_status=PaymentStatus.SUCCEEDED,
        provider_reference="PROVIDER-UNKNOWN",
        expected_version=pending.resource_version,
    )
    assert resolved.status == BookingStatus.COMPENSATION_PENDING
    assert resolved.compensation_action == CompensationAction.RELEASE_AND_REFUND
    assert resolved.payment_status == PaymentStatus.REFUND_PENDING

    failed = service.record_compensation(
        context(),
        idempotency_key="COMPENSATE-UNKNOWN",
        booking_id=booking.booking_id,
        expected_version=resolved.resource_version,
        compensation_status=CompensationStatus.COMPLETED,
        evidence=CompensationEvidence(
            reservation_released=True,
            payment_refunded=True,
            provider_reference="REF-UNKNOWN",
            verified_at=datetime.now(UTC),
        ),
    )
    assert failed.status == BookingStatus.FAILED
    assert failed.payment_status == PaymentStatus.REFUNDED


def test_partial_compensation_evidence_is_persisted_without_being_ignored(
    service: BookingService,
) -> None:
    booking = create(service, key="CREATE-PARTIAL")
    ticketed = successful_evidence(
        service,
        booking.booking_id,
        booking.resource_version,
        prefix="PARTIAL",
        reservation_id="RES-PARTIAL",
        payment_id="PAY-PARTIAL",
    )
    confirmed = confirm_booking(
        service,
        booking.booking_id,
        ticketed.resource_version,
        key="CONFIRM-PARTIAL",
    )
    pending = service.cancel(
        context(),
        idempotency_key="CANCEL-PARTIAL",
        booking_id=booking.booking_id,
        reason="customer requested cancellation",
        expected_version=confirmed.resource_version,
    )

    released = service.record_compensation(
        context(),
        idempotency_key="PARTIAL-RELEASE",
        booking_id=booking.booking_id,
        expected_version=pending.resource_version,
        compensation_status=CompensationStatus.PENDING,
        evidence=CompensationEvidence(
            reservation_released=True,
            verified_at=datetime.now(UTC),
        ),
    )
    assert released.status == BookingStatus.COMPENSATION_PENDING
    assert released.reservation_status == ReservationEvidenceStatus.RELEASED
    assert released.payment_status == PaymentStatus.REFUND_PENDING

    completed = service.record_compensation(
        context(),
        idempotency_key="PARTIAL-REFUND",
        booking_id=booking.booking_id,
        expected_version=released.resource_version,
        compensation_status=CompensationStatus.COMPLETED,
        evidence=CompensationEvidence(
            payment_refunded=True,
            provider_reference="REF-PARTIAL",
            verified_at=datetime.now(UTC),
        ),
    )
    assert completed.status == BookingStatus.CANCELLED


def test_ordering_guards_and_reconciliation_recommendations(
    service: BookingService,
) -> None:
    booking = create(service, key="CREATE-GUARDS")
    with pytest.raises(InvalidRequest):
        service.start_payment(
            context(),
            idempotency_key="START-TOO-EARLY",
            booking_id=booking.booking_id,
            payment_id="PAY-EARLY",
            expected_version=booking.resource_version,
        )

    reserved = attach_hold(
        service,
        booking.booking_id,
        booking.resource_version,
        reservation_id="RES-GUARDS",
        key="RESERVE-GUARDS",
    )
    with pytest.raises(MissingPaymentEvidence):
        service.confirm_reservation(
            context(),
            idempotency_key="CONFIRM-SEAT-TOO-EARLY",
            booking_id=booking.booking_id,
            reservation_id="RES-GUARDS",
            expected_version=reserved.resource_version,
        )
    with pytest.raises(MissingReservationEvidence):
        service.confirm(
            context(),
            idempotency_key="CONFIRM-NOT-READY",
            booking_id=booking.booking_id,
            expected_version=reserved.resource_version,
        )

    page = service.reconcile(older_than_seconds=0, page=1, page_size=100)
    candidate = next(
        item for item in page.items if item.booking_id == booking.booking_id
    )
    assert candidate.missing_evidence == ("PAYMENT",)
    assert candidate.recommended_action == "START_PAYMENT"


def test_idempotency_and_reservation_conflicts_are_stable(
    service: BookingService,
) -> None:
    create(service, key="CREATE-IDEMPOTENT")
    with pytest.raises(IdempotencyConflict):
        create(
            service,
            key="CREATE-IDEMPOTENT",
            customer_id="C999",
        )

    first = create(
        service,
        key="CREATE-LEGACY-1",
        reservation_id="RES-LEGACY",
    )
    replay = create(
        service,
        key="CREATE-LEGACY-2",
        reservation_id="RES-LEGACY",
    )
    assert replay.booking_id == first.booking_id
    with pytest.raises(ReservationConflict):
        create(
            service,
            key="CREATE-LEGACY-3",
            customer_id="C999",
            reservation_id="RES-LEGACY",
        )


def test_database_rejects_inconsistent_intermediate_state(
    service: BookingService,
) -> None:
    booking = create(service, key="CREATE-CONSTRAINT")
    with pytest.raises(IntegrityError):
        with service.session_factory() as session:
            with session.begin():
                session.execute(
                    text(
                        "UPDATE booking.bookings SET payment_status = 'FAILED' "
                        "WHERE booking_id = :booking_id"
                    ),
                    {"booking_id": booking.booking_id},
                )


@pytest.mark.concurrency
def test_concurrent_attach_of_one_reservation_has_one_owner(
    service: BookingService,
) -> None:
    first = create(service, key="CREATE-RACE-1", customer_id="C001")
    second = create(service, key="CREATE-RACE-2", customer_id="C002")

    def worker(booking_id: str, key: str) -> tuple[str, str]:
        try:
            result = service.attach_reservation(
                context(f"COR-{key}"),
                idempotency_key=key,
                booking_id=booking_id,
                reservation_id="RES-RACE",
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
                confirmed=False,
                expected_version=1,
            )
            return ("ok", result.booking_id)
        except ReservationConflict:
            return ("conflict", booking_id)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                lambda args: worker(*args),
                ((first.booking_id, "RACE-1"), (second.booking_id, "RACE-2")),
            )
        )

    assert sorted(outcome for outcome, _ in outcomes) == ["conflict", "ok"]
    page = service.list(
        page=1,
        page_size=20,
        customer_id=None,
        event_id=None,
        status=BookingStatus.SEAT_RESERVED,
        search=None,
    )
    assert page.total == 1
    assert page.items[0].reservation_id == "RES-RACE"
