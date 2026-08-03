"""GetBooking query."""

from sqlalchemy.orm import Session

from app.application.common import prepare_transaction
from app.config import Settings
from app.domain.entities import Booking
from app.domain.exceptions import BookingNotFound
from app.domain.rules import validate_identifier
from app.infrastructure.database.repositories import get_booking_model, model_to_entity


def get_booking(session: Session, settings: Settings, booking_id: str) -> Booking:
    booking_id = validate_identifier(booking_id, "bookingId")
    with session.begin():
        prepare_transaction(session, settings)
        model = get_booking_model(session, booking_id)
        if model is None:
            raise BookingNotFound(booking_id)
        return model_to_entity(model)
