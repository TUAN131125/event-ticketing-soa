"""Use case: mo ban ve (DRAFT/PAUSED -> ON_SALE)."""

from app.domain.entities import Event
from app.domain.enums import EventStatus
from app.domain.exceptions import EventNotFoundError, InvalidStateTransitionError
from app.domain.rules import ensure_transition_allowed
from app.repositories.interfaces import EventRepository


def open_sales(
    repo: EventRepository, event_id: str, expected_version: int | None = None
) -> Event:
    event = repo.get(event_id)
    if event is None:
        raise EventNotFoundError(event_id)
    if expected_version is not None and event.resource_version != expected_version:
        raise InvalidStateTransitionError(
            str(event.resource_version), str(expected_version)
        )
    ensure_transition_allowed(event.status, EventStatus.ON_SALE)
    event.status = EventStatus.ON_SALE
    event.touch()
    repo.update(event)
    return event
