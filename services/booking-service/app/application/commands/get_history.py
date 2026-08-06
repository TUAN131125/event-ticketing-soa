"""Read immutable booking transition history."""

from sqlalchemy.orm import Session

from app.application.common import prepare_transaction
from app.config import Settings
from app.domain.exceptions import BookingNotFound
from app.domain.rules import validate_identifier
from app.domain.value_objects import BookingHistoryEntry
from app.infrastructure.database.repositories import (
    get_booking_model,
    list_booking_history,
)


def get_history(
    session: Session, settings: Settings, booking_id: str
) -> tuple[BookingHistoryEntry, ...]:
    normalized = validate_identifier(booking_id, "bookingId")
    with session.begin():
        prepare_transaction(session, settings)
        if get_booking_model(session, normalized) is None:
            raise BookingNotFound(normalized)
        return list_booking_history(session, normalized)
