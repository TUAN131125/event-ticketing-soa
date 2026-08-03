"""Paginated ListPayments query."""

from sqlalchemy.orm import Session

from app.application.common import prepare_transaction
from app.config import Settings
from app.domain.enums import PaymentStatus
from app.domain.exceptions import InvalidRequest
from app.domain.rules import validate_identifier
from app.domain.value_objects import PaymentPage
from app.infrastructure.database.repositories import (
    list_payment_models,
    model_to_entity,
)


def list_payments(
    session: Session,
    settings: Settings,
    *,
    page: int,
    page_size: int,
    booking_id: str | None,
    customer_id: str | None,
    provider: str | None,
    status: PaymentStatus | None,
    search: str | None,
) -> PaymentPage:
    if page < 1:
        raise InvalidRequest("page must be at least 1")
    if not 1 <= page_size <= 100:
        raise InvalidRequest("pageSize must be between 1 and 100")
    if booking_id is not None:
        booking_id = validate_identifier(booking_id, "bookingId")
    if customer_id is not None:
        customer_id = validate_identifier(customer_id, "customerId")
    if provider is not None:
        provider = validate_identifier(provider, "provider", max_length=40)
    if search is not None:
        search = search.strip()
        if not 1 <= len(search) <= 128:
            raise InvalidRequest("search must be between 1 and 128 characters")
    with session.begin():
        prepare_transaction(session, settings)
        models, total = list_payment_models(
            session,
            page=page,
            page_size=page_size,
            booking_id=booking_id,
            customer_id=customer_id,
            provider=provider,
            status=status,
            search=search,
        )
        return PaymentPage(
            items=tuple(model_to_entity(model) for model in models),
            page=page,
            page_size=page_size,
            total=total,
        )
