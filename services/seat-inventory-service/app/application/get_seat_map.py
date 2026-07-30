"""GetSeatMap snapshot query."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.application.common import RequestContext
from app.domain.exceptions import EventNotFound
from app.domain.seat import SeatView
from app.infrastructure.database.repositories import (
    database_now,
    get_inventory_version,
    get_seats,
    seat_to_view,
)


@dataclass(frozen=True, slots=True)
class SeatMapResult:
    event_id: str
    inventory_version: int
    generated_at: datetime
    seats: tuple[SeatView, ...]


def get_seat_map(
    session: Session, context: RequestContext, event_id: str
) -> SeatMapResult:
    context.validated()
    version = get_inventory_version(session, event_id)
    if version is None:
        raise EventNotFound(event_id)
    return SeatMapResult(
        event_id=event_id,
        inventory_version=version,
        generated_at=database_now(session),
        seats=tuple(seat_to_view(seat) for seat in get_seats(session, event_id)),
    )
