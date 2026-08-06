"""CountBookingsByStatus query backing the booking status gauge."""

from collections.abc import Sequence

from sqlalchemy.orm import Session

from app.application.common import prepare_transaction
from app.config import Settings
from app.infrastructure.database.repositories import booking_counts_by_status


def count_bookings_by_status(
    session: Session, settings: Settings
) -> Sequence[tuple[str, int]]:
    with session.begin():
        prepare_transaction(session, settings)
        return booking_counts_by_status(session)
