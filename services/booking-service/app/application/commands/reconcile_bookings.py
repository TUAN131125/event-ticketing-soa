"""Resume/Reconcile query for non-terminal or compensation-pending bookings."""

from datetime import timedelta

from sqlalchemy.orm import Session

from app.application.common import prepare_transaction
from app.config import Settings
from app.domain.entities import Booking
from app.domain.enums import (
    BookingStatus,
    CompensationAction,
    PaymentStatus,
    RecoveryAction,
    ReservationEvidenceStatus,
)
from app.domain.exceptions import InvalidRequest
from app.domain.value_objects import ReconciliationCandidate, ReconciliationPage
from app.infrastructure.database.mappers import model_to_entity
from app.infrastructure.database.repositories import (
    database_now,
    list_stuck_booking_models,
)


def reconcile_bookings(
    session: Session,
    settings: Settings,
    *,
    older_than_seconds: int,
    page: int,
    page_size: int,
) -> ReconciliationPage:
    if page < 1:
        raise InvalidRequest("page must be at least 1")
    if not 1 <= page_size <= 100:
        raise InvalidRequest("pageSize must be between 1 and 100")
    if not 0 <= older_than_seconds <= 2_592_000:
        raise InvalidRequest("olderThanSeconds must be between 0 and 2592000")
    with session.begin():
        prepare_transaction(session, settings)
        cutoff = database_now(session) - timedelta(seconds=older_than_seconds)
        models, total = list_stuck_booking_models(
            session, older_than=cutoff, page=page, page_size=page_size
        )
        return ReconciliationPage(
            items=tuple(_candidate(model_to_entity(model)) for model in models),
            page=page,
            page_size=page_size,
            total=total,
        )


def _candidate(booking: Booking) -> ReconciliationCandidate:
    missing: list[str] = []
    action = RecoveryAction.NO_ACTION

    if booking.status == BookingStatus.COMPENSATION_PENDING:
        if booking.payment_status == PaymentStatus.UNKNOWN:
            missing.append("PAYMENT_OUTCOME")
            action = RecoveryAction.RECONCILE_PAYMENT
        else:
            if booking.compensation_action in {
                CompensationAction.RELEASE_RESERVATION,
                CompensationAction.RELEASE_AND_REFUND,
            } and booking.reservation_status != ReservationEvidenceStatus.RELEASED:
                missing.append("RESERVATION_RELEASE")
            if booking.compensation_action in {
                CompensationAction.REFUND_PAYMENT,
                CompensationAction.RELEASE_AND_REFUND,
            } and booking.payment_status != PaymentStatus.REFUNDED:
                missing.append("PAYMENT_REFUND")
            action = RecoveryAction.COMPLETE_COMPENSATION
    elif booking.status == BookingStatus.PENDING:
        missing.append("RESERVATION")
        action = RecoveryAction.ATTACH_RESERVATION
    elif booking.status == BookingStatus.SEAT_RESERVED:
        if booking.reservation_status not in {
            ReservationEvidenceStatus.RESERVED,
            ReservationEvidenceStatus.CONFIRMED,
        }:
            missing.append("RESERVATION")
            action = RecoveryAction.ATTACH_RESERVATION
        else:
            missing.append("PAYMENT")
            action = RecoveryAction.START_PAYMENT
    elif booking.status == BookingStatus.PAYMENT_PROCESSING:
        if booking.payment_status in {PaymentStatus.PENDING, PaymentStatus.PROCESSING}:
            missing.append("PAYMENT_OUTCOME")
            action = RecoveryAction.QUERY_PAYMENT
        elif booking.payment_status == PaymentStatus.UNKNOWN:
            missing.append("PAYMENT_OUTCOME")
            action = RecoveryAction.RECONCILE_PAYMENT
        elif booking.payment_status == PaymentStatus.FAILED:
            if booking.reservation_status != ReservationEvidenceStatus.RELEASED:
                missing.append("RESERVATION_RELEASE")
            action = RecoveryAction.RELEASE_RESERVATION_AND_FAIL
        elif booking.payment_status == PaymentStatus.SUCCEEDED:
            if booking.reservation_status != ReservationEvidenceStatus.CONFIRMED:
                missing.append("RESERVATION_CONFIRMATION")
                action = RecoveryAction.CONFIRM_RESERVATION
            elif not booking.ticket_ids:
                missing.append("TICKETS")
                action = RecoveryAction.ISSUE_TICKETS
            else:
                action = RecoveryAction.CONFIRM_BOOKING

    return ReconciliationCandidate(
        booking_id=booking.booking_id,
        status=booking.status.value,
        missing_evidence=tuple(missing),
        recommended_action=action.value,
        resource_version=booking.resource_version,
        updated_at=booking.updated_at,
        compensation_status=booking.compensation_status.value,
        compensation_action=booking.compensation_action.value,
    )
