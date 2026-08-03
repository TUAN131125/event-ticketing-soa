"""Atomic and idempotent FailBooking command."""

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
    validate_reason,
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

SCOPE = "FailBooking"


def fail_booking(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    booking_id: str,
    failure_code: str,
    reason: str,
    expected_version: int,
) -> Booking:
    key = validate_context(context, idempotency_key)
    booking_id = validate_identifier(booking_id, "bookingId")
    failure_code = validate_identifier(failure_code, "failureCode")
    reason = validate_reason(reason)
    expected_version = validate_expected_version(expected_version)
    request_hash = canonical_request_hash(
        {
            "bookingId": booking_id,
            "failureCode": failure_code,
            "reason": reason,
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
        if booking.status == BookingStatus.FAILED:
            if (
                booking.failure_code != failure_code
                or booking.failure_reason != reason.strip()
            ):
                raise InvalidRequest(
                    "Failed booking already records another failure reason"
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
        previous = booking.status
        booking.fail(
            failure_code=failure_code,
            reason=reason,
            expected_version=expected_version,
            now=now,
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
            details={"failureCode": booking.failure_code},
        )
        append_outbox_event(
            session,
            booking=booking,
            event_type=BookingEventType.FAILED,
            payload={
                **event_payload(booking),
                "failureCode": booking.failure_code,
                "reason": booking.failure_reason,
            },
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
