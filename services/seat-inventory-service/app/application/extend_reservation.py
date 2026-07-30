"""Idempotent ExtendReservation command with optimistic version control."""

from __future__ import annotations

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
from app.domain.exceptions import (
    InvalidReservationState,
    ReservationExpired,
    ReservationNotFound,
    VersionConflict,
)
from app.domain.reservation import ReservationStatus, ReservationView
from app.domain.rules import (
    canonical_request_hash,
    validate_extension_seconds,
    validate_identifier,
)
from app.infrastructure.database.repositories import (
    database_now,
    get_reservation,
    reservation_to_view,
)

SCOPE = "ExtendReservation"


def extend_reservation(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    reservation_id: str,
    expected_version: int,
    extension_seconds: int,
) -> ReservationView:
    context.validated(require_idempotency=True)
    reservation_id = validate_identifier(reservation_id, "reservationId")
    extension_seconds = validate_extension_seconds(
        extension_seconds, settings.max_extension_seconds
    )
    request_hash = canonical_request_hash(
        {
            "reservationId": reservation_id,
            "expectedVersion": expected_version,
            "extensionSeconds": extension_seconds,
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

        reservation = get_reservation(session, reservation_id, for_update=True)
        if reservation is None:
            raise ReservationNotFound(reservation_id)
        now = database_now(session)
        if reservation.status != ReservationStatus.ACTIVE:
            raise InvalidReservationState(reservation_id, reservation.status)
        if reservation.expires_at <= now:
            raise ReservationExpired(reservation_id)
        if reservation.resource_version != expected_version:
            raise VersionConflict(expected_version, reservation.resource_version)
        if reservation.extend_count >= settings.max_extend_count:
            raise InvalidReservationState(reservation_id, "MAX_EXTENSION_REACHED")

        reservation.expires_at += timedelta(seconds=extension_seconds)
        reservation.extend_count += 1
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
