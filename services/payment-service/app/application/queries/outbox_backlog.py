"""Outbox backlog counters, shared by the API metrics endpoint and the relay."""

from sqlalchemy.orm import Session

from app.application.common import prepare_transaction
from app.config import Settings
from app.infrastructure.database.repositories import count_outbox_backlog


def outbox_backlog(session: Session, settings: Settings) -> tuple[int, int]:
    """Return (pending, exhausted) counts for unpublished outbox events."""
    with session.begin():
        prepare_transaction(session, settings)
        return count_outbox_backlog(session, max_attempts=settings.outbox_max_attempts)
