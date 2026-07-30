"""Atomic, idempotent ReserveSeats command."""

from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy.orm import Session

from app.application.common import (
    RequestContext,
    prepare_transaction,
    replay_or_lock,
    reservation_from_payload,
    reservation_to_payload,
    save_replay,
)
from app.config import Settings
from app.domain.exceptions import InventoryConflict, SeatNotFound, SeatUnavailable
from app.domain.reservation import ReservationStatus, ReservationView
from app.domain.rules import (
    canonical_request_hash,
    normalize_seat_ids,
    validate_hold_seconds,
    validate_identifier,
)
from app.domain.seat import SeatStatus
from app.infrastructure.database.models import (
    ReservationItemModel,
    ReservationModel,
)
from app.infrastructure.database.repositories import (
    append_audit,
    database_now,
    get_reservation_by_booking,
    lock_seats,
    reservation_to_view,
)
from app.observability.metrics import RESERVE_CONFLICT_TOTAL

SCOPE = "ReserveSeats"


def reserve_seats(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    booking_id: str,
    event_id: str,
    seat_ids: tuple[str, ...],
    hold_seconds: int,
) -> ReservationView:
    context.validated(require_idempotency=True)
    booking_id = validate_identifier(booking_id, "bookingId")
    event_id = validate_identifier(event_id, "eventId")
    normalized_seats = normalize_seat_ids(seat_ids)
    hold_seconds = validate_hold_seconds(
        hold_seconds, settings.min_hold_seconds, settings.max_hold_seconds
    )
    request_hash = canonical_request_hash(
        {
            "bookingId": booking_id,
            "eventId": event_id,
            "seatIds": normalized_seats,
            "holdSeconds": hold_seconds,
        }
    )
    idempotency_key = context.idempotency_key
    if idempotency_key is None:
        raise AssertionError("validated idempotency key is missing")

    with session.begin():
        prepare_transaction(session, settings)
        replay = replay_or_lock(
            session,
            scope=SCOPE,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        if replay is not None:
            return reservation_from_payload(replay)

        existing = get_reservation_by_booking(session, booking_id, for_update=True)
        if existing is not None:
            existing_view = reservation_to_view(session, existing)
            if (
                existing_view.event_id != event_id
                or existing_view.seat_ids != normalized_seats
            ):
                raise InventoryConflict(
                    f"Booking {booking_id} already owns a different reservation"
                )
            now = database_now(session)
            payload = reservation_to_payload(existing_view)
            save_replay(
                session,
                settings=settings,
                scope=SCOPE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response=payload,
                resource_id=existing_view.reservation_id,
                now=now,
            )
            return existing_view

        seats = lock_seats(session, event_id, normalized_seats)
        found = {seat.seat_id for seat in seats}
        missing = sorted(set(normalized_seats) - found)
        if missing:
            raise SeatNotFound(missing)
        unavailable = sorted(
            seat.seat_id for seat in seats if seat.status != SeatStatus.AVAILABLE
        )
        if unavailable:
            RESERVE_CONFLICT_TOTAL.inc()
            raise SeatUnavailable(unavailable)

        now = database_now(session)
        reservation = ReservationModel(
            reservation_id=str(uuid.uuid4()),
            booking_id=booking_id,
            event_id=event_id,
            status=ReservationStatus.ACTIVE,
            expires_at=now + timedelta(seconds=hold_seconds),
            extend_count=0,
            resource_version=1,
            created_at=now,
            updated_at=now,
        )
        session.add(reservation)
        session.flush()

        for seat in seats:
            session.add(
                ReservationItemModel(
                    reservation_id=reservation.reservation_id,
                    event_id=event_id,
                    seat_id=seat.seat_id,
                    created_at=now,
                )
            )
            previous = seat.status
            seat.status = SeatStatus.HELD
            seat.current_reservation_id = reservation.reservation_id
            seat.resource_version += 1
            seat.updated_at = now
            append_audit(
                session,
                event_id=event_id,
                seat_id=seat.seat_id,
                reservation_id=reservation.reservation_id,
                booking_id=booking_id,
                operation=SCOPE,
                previous_status=previous,
                new_status=seat.status,
                reason_code="BOOKING_HOLD",
                actor_id=context.actor_id,
                caller_service=context.caller_service,
                correlation_id=context.correlation_id,
                idempotency_key=idempotency_key,
                resource_version=seat.resource_version,
            )

        view = ReservationView(
            reservation_id=reservation.reservation_id,
            booking_id=booking_id,
            event_id=event_id,
            seat_ids=normalized_seats,
            status=ReservationStatus.ACTIVE,
            expires_at=reservation.expires_at,
            extend_count=0,
            resource_version=1,
            created_at=now,
            updated_at=now,
        )
        payload = reservation_to_payload(view)
        save_replay(
            session,
            settings=settings,
            scope=SCOPE,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response=payload,
            resource_id=reservation.reservation_id,
            now=now,
        )
        return view
