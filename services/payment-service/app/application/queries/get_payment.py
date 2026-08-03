"""GetPayment query."""

from sqlalchemy.orm import Session

from app.application.common import prepare_transaction
from app.config import Settings
from app.domain.entities import Payment
from app.domain.exceptions import PaymentNotFound
from app.domain.rules import validate_identifier
from app.infrastructure.database.repositories import get_payment_model, model_to_entity


def get_payment(session: Session, settings: Settings, payment_id: str) -> Payment:
    payment_id = validate_identifier(payment_id, "paymentId")
    with session.begin():
        prepare_transaction(session, settings)
        model = get_payment_model(session, payment_id)
        if model is None:
            raise PaymentNotFound(payment_id)
        return model_to_entity(model)
