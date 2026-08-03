"""Atomic and idempotent CreateBooking command."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

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
from app.domain.exceptions import ReservationConflict
from app.domain.rules import advisory_lock_id, canonical_request_hash
from app.domain.value_objects import BookingItem, RequestContext
from app.infrastructure.database.repositories import (
    acquire_advisory_lock,
    append_audit,
    append_outbox_event,
    database_now,
    entity_to_model,
    get_booking_by_reservation,
    model_to_entity,
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
    reservation_id: str,
    payment_method: str,
    items: tuple[BookingItem, ...],
    total_amount: Decimal,
    currency: str,
) -> Booking:
    key = validate_context(context, idempotency_key)
    candidate = Booking.create(
        booking_id="BK-COMPARE",
        customer_id=customer_id,
        event_id=event_id,
        reservation_id=reservation_id,
        payment_method=payment_method,
        items=items,
        total_amount=total_amount,
        currency=currency,
        now=datetime.now(UTC),
    )
    customer_id = candidate.customer_id
    event_id = candidate.event_id
    reservation_id = candidate.reservation_id
    payment_method = candidate.payment_method
    items = candidate.items
    total_amount = candidate.total_amount
    currency = candidate.currency
    request = _creation_payload(candidate)
    request_hash = canonical_request_hash(request)

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

        acquire_advisory_lock(
            session, advisory_lock_id("BookingReservation", reservation_id)
        )
        existing_model = get_booking_by_reservation(
            session, reservation_id, for_update=True
        )
        if existing_model is not None:
            existing = model_to_entity(existing_model)
            if _creation_payload(existing) != request:
                raise ReservationConflict(reservation_id)
            save_replay(
                session,
                settings=settings,
                scope=SCOPE,
                key=key,
                request_hash=request_hash,
                booking=existing,
                now=now,
            )
            return existing

        booking = Booking.create(
            booking_id=next_booking_id(session),
            customer_id=customer_id,
            event_id=event_id,
            reservation_id=reservation_id,
            payment_method=payment_method,
            items=items,
            total_amount=total_amount,
            currency=currency,
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
    return {
        key: payload[key]
        for key in (
            "customerId",
            "eventId",
            "reservationId",
            "paymentMethod",
            "items",
            "totalAmount",
            "currency",
        )
    }
