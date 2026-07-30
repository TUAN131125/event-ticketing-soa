"""GetReservation authoritative query."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.application.common import RequestContext
from app.domain.exceptions import ReservationNotFound
from app.domain.reservation import ReservationView
from app.domain.rules import validate_identifier
from app.infrastructure.database.repositories import (
    get_reservation,
    reservation_to_view,
)


def get_reservation_view(
    session: Session, context: RequestContext, reservation_id: str
) -> ReservationView:
    context.validated()
    reservation_id = validate_identifier(reservation_id, "reservationId")
    model = get_reservation(session, reservation_id)
    if model is None:
        raise ReservationNotFound(reservation_id)
    return reservation_to_view(session, model)
