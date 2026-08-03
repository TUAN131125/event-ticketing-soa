"""Atomic and idempotent ConfirmBooking command."""

from sqlalchemy.orm import Session

from app.application.common import (
    event_payload,
    prepare_transaction,
    replay_or_lock,
    save_replay,
    validate_context,
)
from app.config import Settings
from app.domain.entities import Booking
from app.domain.enums import BookingEventType, BookingStatus
from app.domain.exceptions import BookingNotFound, InvalidRequest
from app.domain.rules import (
    canonical_request_hash,
    validate_expected_version,
    validate_identifier,
)
from app.domain.value_objects import RequestContext
from app.infrastructure.database.repositories import (
    append_audit,
    append_outbox_event,
    apply_entity,
    database_now,
    get_booking_model,
    model_to_entity,
)

SCOPE = "ConfirmBooking"


def confirm_booking(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    booking_id: str,
    payment_id: str,
    expected_version: int,
) -> Booking:
    key = validate_context(context, idempotency_key)
    booking_id = validate_identifier(booking_id, "bookingId")
    payment_id = validate_identifier(payment_id, "paymentId")
    expected_version = validate_expected_version(expected_version)
    request_hash = canonical_request_hash(
        {
            "bookingId": booking_id,
            "paymentId": payment_id,
            "expectedVersion": expected_version,
        }
    )
    with session.begin():
        prepare_transaction(session, settings)
        now = database_now(session)
        replay = replay_or_lock(
            session,
            scope=SCOPE,
            key=key,
            request_hash=request_hash,
            now=now,
        )
        if replay is not None:
            return replay
        model = get_booking_model(session, booking_id, for_update=True)
        if model is None:
            raise BookingNotFound(booking_id)
        booking = model_to_entity(model)
        if booking.status == BookingStatus.CONFIRMED:
            if booking.payment_id != payment_id:
                raise InvalidRequest("Confirmed booking is attached to another payment")
            save_replay(
                session,
                settings=settings,
                scope=SCOPE,
                key=key,
                request_hash=request_hash,
                booking=booking,
                now=now,
            )
            return booking
        previous = booking.status
        booking.confirm(
            payment_id=payment_id, expected_version=expected_version, now=now
        )
        apply_entity(model, booking)
        append_audit(
            session,
            booking=booking,
            operation=SCOPE,
            previous_status=previous,
            caller_service=context.caller_service,
            actor_id=context.actor_id,
            correlation_id=context.correlation_id,
            idempotency_key=key,
            details={"paymentId": booking.payment_id},
        )
        append_outbox_event(
            session,
            booking=booking,
            event_type=BookingEventType.CONFIRMED,
            payload=event_payload(booking),
            correlation_id=context.correlation_id,
            now=now,
        )
        save_replay(
            session,
            settings=settings,
            scope=SCOPE,
            key=key,
            request_hash=request_hash,
            booking=booking,
            now=now,
        )
        return booking
