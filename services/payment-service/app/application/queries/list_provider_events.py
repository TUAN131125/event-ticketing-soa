"""Read immutable provider events for one payment."""

from sqlalchemy.orm import Session

from app.application.common import prepare_transaction
from app.config import Settings
from app.domain.exceptions import PaymentNotFound
from app.domain.rules import validate_identifier
from app.domain.value_objects import ProviderEvent
from app.infrastructure.database.repositories import (
    get_payment_model,
    list_provider_events,
)


def query_provider_events(
    session: Session, settings: Settings, payment_id: str
) -> tuple[ProviderEvent, ...]:
    payment_id = validate_identifier(payment_id, "paymentId")
    with session.begin():
        prepare_transaction(session, settings)
        if get_payment_model(session, payment_id) is None:
            raise PaymentNotFound(payment_id)
        return list_provider_events(session, payment_id)
