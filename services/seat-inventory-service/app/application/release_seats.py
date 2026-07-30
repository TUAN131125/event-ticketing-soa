"""Atomic, idempotent ReleaseSeats compensation command."""

from __future__ import annotations

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
from app.domain.exceptions import (
    InvalidReservationState,
    ReservationNotFound,
)
from app.domain.reservation import ReservationStatus, ReservationView
from app.domain.rules import canonical_request_hash, validate_identifier
from app.domain.seat import SeatStatus
from app.infrastructure.database.repositories import (
    append_audit,
    database_now,
    get_reservation,
    lock_reservation_seats,
    reservation_to_view,
)

SCOPE = "ReleaseSeats"


def release_seats(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    reservation_id: str,
    reason_code: str,
) -> ReservationView:
    context.validated(require_idempotency=True)
    reservation_id = validate_identifier(reservation_id, "reservationId")
    reason_code = validate_identifier(reason_code, "reasonCode")
    request_hash = canonical_request_hash(
        {"reservationId": reservation_id, "reasonCode": reason_code}
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

        reservation = get_reservation(session, reservation_id, for_update=True)
        if reservation is None:
            raise ReservationNotFound(reservation_id)
        now = database_now(session)

        if reservation.status in {
            ReservationStatus.RELEASED,
            ReservationStatus.EXPIRED,
        }:
            view = reservation_to_view(session, reservation)
            payload = reservation_to_payload(view)
            save_replay(
                session,
                settings=settings,
                scope=SCOPE,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                response=payload,
                resource_id=reservation_id,
                now=now,
            )
            return view
        if reservation.status != ReservationStatus.ACTIVE:
            raise InvalidReservationState(reservation_id, reservation.status)

        seats = lock_reservation_seats(session, reservation_id)
        if not seats or any(
            seat.status != SeatStatus.HELD
            or seat.current_reservation_id != reservation_id
            for seat in seats
        ):
            raise InvalidReservationState(reservation_id, "INCONSISTENT_SEAT_HOLD")

        for seat in seats:
            previous = seat.status
            seat.status = SeatStatus.AVAILABLE
            seat.current_reservation_id = None
            seat.resource_version += 1
            seat.updated_at = now
            append_audit(
                session,
                event_id=reservation.event_id,
                seat_id=seat.seat_id,
                reservation_id=reservation_id,
                booking_id=reservation.booking_id,
                operation=SCOPE,
                previous_status=previous,
                new_status=seat.status,
                reason_code=reason_code,
                actor_id=context.actor_id,
                caller_service=context.caller_service,
                correlation_id=context.correlation_id,
                idempotency_key=idempotency_key,
                resource_version=seat.resource_version,
            )

        reservation.status = ReservationStatus.RELEASED
        reservation.resource_version += 1
        reservation.updated_at = now
        view = reservation_to_view(session, reservation)
        payload = reservation_to_payload(view)
        save_replay(
            session,
            settings=settings,
            scope=SCOPE,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            response=payload,
            resource_id=reservation_id,
            now=now,
        )
        return view
