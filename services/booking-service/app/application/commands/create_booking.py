"""Atomic and idempotent CreateBooking command."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

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
from app.domain.enums import BookingEventType
from app.domain.exceptions import ReservationConflict
from app.domain.rules import (
    advisory_lock_id,
    canonical_request_hash,
    normalize_new_booking,
)
from app.domain.value_objects import BookingItem, NewBookingRequest, RequestContext
from app.infrastructure.database.mappers import entity_to_model, model_to_entity
from app.infrastructure.database.repositories import (
    acquire_advisory_lock,
    append_audit,
    append_outbox_event,
    database_now,
    get_booking_by_reservation,
    next_booking_id,
)

SCOPE = "CreateBooking"
RESERVATION_LOCK_SCOPE = "BookingReservation"


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
    total_amount: Decimal | None = None,
    reservation_id: str | None = None,
    payment_method: str | None = None,
) -> Booking:
    key = validate_context(context, idempotency_key)
    request = normalize_new_booking(
        customer_id=customer_id,
        event_id=event_id,
        reservation_id=reservation_id,
        payment_method=payment_method,
        items=items,
        total_amount=total_amount,
        currency=currency,
    )
    payload = _creation_payload(request)
    request_hash = canonical_request_hash(payload)

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

        existing = _claim_reservation(session, request, payload)
        booking = existing or _open_booking(session, context, request, key, now)
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


def _claim_reservation(
    session: Session,
    request: NewBookingRequest,
    creation_payload: dict[str, Any],
) -> Booking | None:
    if request.reservation_id is None:
        return None
    acquire_advisory_lock(
        session, advisory_lock_id(RESERVATION_LOCK_SCOPE, request.reservation_id)
    )
    model = get_booking_by_reservation(
        session, request.reservation_id, for_update=True
    )
    if model is None:
        return None
    booking = model_to_entity(model)
    if _booking_creation_payload(booking) != creation_payload:
        raise ReservationConflict(request.reservation_id)
    return booking


def _open_booking(
    session: Session,
    context: RequestContext,
    request: NewBookingRequest,
    idempotency_key: str,
    now: datetime,
) -> Booking:
    booking = Booking.from_request(
        booking_id=next_booking_id(session), request=request, now=now
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
        idempotency_key=idempotency_key,
        details={"priceSnapshotTotal": str(booking.total_amount)},
    )
    append_outbox_event(
        session,
        booking=booking,
        event_type=BookingEventType.CREATED,
        payload=event_payload(booking),
        correlation_id=context.correlation_id,
        now=now,
    )
    return booking


def _creation_payload(request: NewBookingRequest) -> dict[str, Any]:
    return {
        "customerId": request.customer_id,
        "eventId": request.event_id,
        "reservationId": request.reservation_id,
        "paymentMethod": request.payment_method,
        "items": [
            {
                "seatId": item.seat_id,
                "ticketType": item.ticket_type,
                "unitPrice": str(item.unit_price),
            }
            for item in request.items
        ],
        "totalAmount": str(request.total_amount),
        "currency": request.currency,
    }


def _booking_creation_payload(booking: Booking) -> dict[str, Any]:
    return {
        "customerId": booking.customer_id,
        "eventId": booking.event_id,
        "reservationId": booking.reservation_id,
        "paymentMethod": booking.payment_method,
        "items": [
            {
                "seatId": item.seat_id,
                "ticketType": item.ticket_type,
                "unitPrice": str(item.unit_price),
            }
            for item in booking.items
        ],
        "totalAmount": str(booking.total_amount),
        "currency": booking.currency,
    }
