"""Locate UNKNOWN payments whose reconciliation backoff has elapsed."""

from sqlalchemy.orm import Session

from app.application.common import prepare_transaction
from app.config import Settings
from app.infrastructure.database.repositories import (
    database_now,
    list_due_unknown_payments,
)


def due_reconciliations(
    session: Session,
    settings: Settings,
    *,
    limit: int,
) -> tuple[tuple[str, int], ...]:
    with session.begin():
        prepare_transaction(session, settings)
        return list_due_unknown_payments(
            session,
            now=database_now(session),
            limit=limit,
        )
