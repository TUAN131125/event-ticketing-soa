"""ListRefunds query."""

from sqlalchemy.orm import Session

from app.application.common import prepare_transaction
from app.config import Settings
from app.domain.exceptions import PaymentNotFound
from app.domain.rules import validate_identifier
from app.domain.value_objects import Refund
from app.infrastructure.database.repositories import (
    get_payment_model,
    list_refund_models,
    refund_model_to_value,
)


def list_refunds(
    session: Session, settings: Settings, payment_id: str
) -> tuple[Refund, ...]:
    payment_id = validate_identifier(payment_id, "paymentId")
    with session.begin():
        prepare_transaction(session, settings)
        if get_payment_model(session, payment_id) is None:
            raise PaymentNotFound(payment_id)
        return tuple(
            refund_model_to_value(model)
            for model in list_refund_models(session, payment_id)
        )
