"""CheckAvailability snapshot query."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.application.common import RequestContext
from app.domain.exceptions import SeatNotFound
from app.domain.rules import normalize_seat_ids, validate_identifier
from app.domain.seat import SeatStatus
from app.infrastructure.database.repositories import database_now, get_seats


@dataclass(frozen=True, slots=True)
class AvailabilityResult:
    event_id: str
    available: bool
    available_seat_ids: tuple[str, ...]
    unavailable_seat_ids: tuple[str, ...]
    checked_at: datetime


def check_availability(
    session: Session,
    context: RequestContext,
    event_id: str,
    seat_ids: tuple[str, ...],
) -> AvailabilityResult:
    context.validated()
    event_id = validate_identifier(event_id, "eventId")
    normalized = normalize_seat_ids(seat_ids)
    seats = get_seats(session, event_id, normalized)
    found = {seat.seat_id for seat in seats}
    missing = sorted(set(normalized) - found)
    if missing:
        raise SeatNotFound(missing)
    available = tuple(
        sorted(seat.seat_id for seat in seats if seat.status == SeatStatus.AVAILABLE)
    )
    unavailable = tuple(sorted(set(normalized) - set(available)))
    return AvailabilityResult(
        event_id=event_id,
        available=not unavailable,
        available_seat_ids=available,
        unavailable_seat_ids=unavailable,
        checked_at=database_now(session),
    )
