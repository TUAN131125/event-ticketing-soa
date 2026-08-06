"""ListCustomerBookings query."""

from sqlalchemy.orm import Session

from app.application.common import prepare_transaction
from app.config import Settings
from app.domain.exceptions import InvalidRequest
from app.domain.rules import validate_identifier
from app.domain.value_objects import BookingPage
from app.infrastructure.database.mappers import model_to_entity
from app.infrastructure.database.repositories import list_booking_models


def list_customer_bookings(
    session: Session,
    settings: Settings,
    *,
    customer_id: str,
    page: int,
    page_size: int,
) -> BookingPage:
    customer_id = validate_identifier(customer_id, "customerId")
    if page < 1:
        raise InvalidRequest("page must be at least 1")
    if not 1 <= page_size <= 100:
        raise InvalidRequest("pageSize must be between 1 and 100")
    with session.begin():
        prepare_transaction(session, settings)
        models, total = list_booking_models(
            session,
            page=page,
            page_size=page_size,
            customer_id=customer_id,
            event_id=None,
            status=None,
            search=None,
        )
        return BookingPage(
            items=tuple(model_to_entity(model) for model in models),
            page=page,
            page_size=page_size,
            total=total,
        )
