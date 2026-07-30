"""Multi-worker-safe expiry command using FOR UPDATE SKIP LOCKED."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.common import RequestContext, prepare_transaction
from app.config import Settings
from app.domain.exceptions import InvalidRequest
from app.domain.reservation import ReservationStatus
from app.domain.seat import SeatStatus
from app.infrastructure.database.models import ReservationModel
from app.infrastructure.database.repositories import (
    append_audit,
    database_now,
    delete_expired_idempotency_records,
    lock_reservation_seats,
)


@dataclass(frozen=True, slots=True)
class ExpiryResult:
    expired_count: int
    reservation_ids: tuple[str, ...]


def expire_reservations(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    batch_size: int | None = None,
) -> ExpiryResult:
    context.validated()
    size = batch_size or settings.expiry_batch_size
    if not 1 <= size <= 1000:
        raise InvalidRequest("batchSize must be between 1 and 1000")

    with session.begin():
        prepare_transaction(session, settings)
        now = database_now(session)
        statement = (
            select(ReservationModel)
            .where(
                ReservationModel.status == ReservationStatus.ACTIVE,
                ReservationModel.expires_at <= now,
            )
            .order_by(ReservationModel.expires_at, ReservationModel.reservation_id)
            .limit(size)
            .with_for_update(skip_locked=True)
        )
        reservations = list(session.execute(statement).scalars())
        expired_ids: list[str] = []
        for reservation in reservations:
            seats = lock_reservation_seats(session, reservation.reservation_id)
            if not seats or any(
                seat.status != SeatStatus.HELD
                or seat.current_reservation_id != reservation.reservation_id
                for seat in seats
            ):
                # Fail closed: an inconsistent allocation is left untouched for
                # reconciliation instead of making a potentially unsafe release.
                continue
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
                    reservation_id=reservation.reservation_id,
                    booking_id=reservation.booking_id,
                    operation="ExpireReservations",
                    previous_status=previous,
                    new_status=seat.status,
                    reason_code="RESERVATION_TTL_EXPIRED",
                    actor_id=context.actor_id,
                    caller_service=context.caller_service,
                    correlation_id=context.correlation_id,
                    idempotency_key=context.idempotency_key,
                    resource_version=seat.resource_version,
                )
            reservation.status = ReservationStatus.EXPIRED
            reservation.resource_version += 1
            reservation.updated_at = now
            expired_ids.append(reservation.reservation_id)

        delete_expired_idempotency_records(session, now)
        return ExpiryResult(
            expired_count=len(expired_ids),
            reservation_ids=tuple(expired_ids),
        )
