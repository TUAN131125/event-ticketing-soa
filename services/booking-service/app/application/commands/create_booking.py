"""Atomic and idempotent canonical CreateBooking command."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.application.common import (
    booking_to_payload,
    event_payload,
    prepare_transaction,
    replay_or_lock,
    save_replay,
    validate_context,
)
from app.config import Settings
from app.domain.entities import Booking
from app.domain.enums import BookingEventType
from app.domain.rules import canonical_request_hash
from app.domain.value_objects import BookingItem, RequestContext
from app.infrastructure.database.repositories import (
    append_audit,
    append_outbox_event,
    database_now,
    entity_to_model,
    next_booking_id,
)

SCOPE = "CreateBooking"


def create_booking(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    customer_id: str,
    event_id: str,
    items: tuple[BookingItem, ...],
    currency: str,
) -> Booking:
    key = validate_context(context, idempotency_key)
    candidate = Booking.create(
        booking_id="BK-COMPARE",
        customer_id=customer_id,
        event_id=event_id,
        items=items,
        currency=currency,
        now=datetime.now(UTC),
    )
    request_hash = canonical_request_hash(_creation_payload(candidate))
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
        booking = Booking.create(
            booking_id=next_booking_id(session),
            customer_id=candidate.customer_id,
            event_id=candidate.event_id,
            items=candidate.items,
            currency=candidate.currency,
            now=now,
        )
        session.add(entity_to_model(booking))
        append_audit(
            session,
            booking=booking,
            operation=SCOPE,
            previous_status=None,
            caller_service=context.caller_service,
            actor_id=context.actor_id,
            correlation_id=context.correlation_id,
            idempotency_key=key,
        )
        append_outbox_event(
            session,
            booking=booking,
            event_type=BookingEventType.CREATED,
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


def _creation_payload(booking: Booking) -> dict[str, object]:
    payload = booking_to_payload(booking)
    return {key: payload[key] for key in ("customerId", "eventId", "items", "total")}
