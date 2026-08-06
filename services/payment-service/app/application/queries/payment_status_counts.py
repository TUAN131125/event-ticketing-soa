"""Payment counts grouped by status, for the metrics gauge."""

from sqlalchemy.orm import Session

from app.application.common import prepare_transaction
from app.config import Settings
from app.infrastructure.database.repositories import payment_counts_by_status


def payment_status_counts(session: Session, settings: Settings) -> dict[str, int]:
    with session.begin():
        prepare_transaction(session, settings)
        return dict(payment_counts_by_status(session))
