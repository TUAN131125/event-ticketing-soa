"""Single canonical transition command with idempotency and If-Match."""

from typing import Any

from sqlalchemy.orm import Session

from app.application.common import (
    prepare_transaction,
    replay_or_lock,
    save_replay,
    validate_context,
)
from app.config import Settings
from app.domain.entities import Booking
from app.domain.exceptions import BookingNotFound
from app.domain.rules import (
    canonical_request_hash,
    validate_expected_version,
    validate_identifier,
)
from app.domain.value_objects import RequestContext
from app.infrastructure.database.repositories import (
    append_audit,
    apply_entity,
    database_now,
    get_booking_model,
    model_to_entity,
)


def transition_booking(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    operation: str,
    booking_id: str,
    payload: dict[str, Any],
    idempotency_key: str,
    expected_version: int,
) -> Booking:
    key = validate_context(context, idempotency_key)
    booking_id = validate_identifier(booking_id, "bookingId")
    expected_version = validate_expected_version(expected_version)
    request_hash = canonical_request_hash(
        {
            "bookingId": booking_id,
            "expectedVersion": expected_version,
            **payload,
        }
    )
    with session.begin():
        prepare_transaction(session, settings)
        now = database_now(session)
        replay = replay_or_lock(
            session,
            scope=operation,
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
        previous = booking.status
        booking.transition(
            operation, payload, expected_version=expected_version, now=now
        )
        apply_entity(model, booking)
        append_audit(
            session,
            booking=booking,
            operation=operation,
            previous_status=previous,
            caller_service=context.caller_service,
            actor_id=context.actor_id,
            correlation_id=context.correlation_id,
            idempotency_key=key,
            details=payload,
        )
        save_replay(
            session,
            settings=settings,
            scope=operation,
            key=key,
            request_hash=request_hash,
            booking=booking,
            now=now,
        )
        return booking
