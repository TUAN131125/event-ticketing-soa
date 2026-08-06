"""Paginated ListBookings query."""

from sqlalchemy.orm import Session

from app.application.common import prepare_transaction
from app.config import Settings
from app.domain.enums import BookingStatus
from app.domain.exceptions import InvalidRequest
from app.domain.rules import validate_identifier
from app.domain.value_objects import BookingPage
from app.infrastructure.database.mappers import model_to_entity
from app.infrastructure.database.repositories import list_booking_models


def list_bookings(
    session: Session,
    settings: Settings,
    *,
    page: int,
    page_size: int,
    customer_id: str | None = None,
    event_id: str | None = None,
    status: BookingStatus | None = None,
    search: str | None = None,
) -> BookingPage:
    if page < 1:
        raise InvalidRequest("page must be at least 1")
    if not 1 <= page_size <= 100:
        raise InvalidRequest("pageSize must be between 1 and 100")
    if customer_id is not None:
        customer_id = validate_identifier(customer_id, "customerId")
    if event_id is not None:
        event_id = validate_identifier(event_id, "eventId")
    if search is not None:
        search = search.strip()
        if not 1 <= len(search) <= 128:
            raise InvalidRequest("search must be between 1 and 128 characters")
    with session.begin():
        prepare_transaction(session, settings)
        models, total = list_booking_models(
            session,
            page=page,
            page_size=page_size,
            customer_id=customer_id,
            event_id=event_id,
            status=status,
            search=search,
        )
        return BookingPage(
            items=tuple(model_to_entity(model) for model in models),
            page=page,
            page_size=page_size,
            total=total,
        )
