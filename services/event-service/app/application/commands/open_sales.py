"""Use case: mo ban ve (DRAFT/PAUSED -> ON_SALE)."""
from app.domain.entities import Event
from app.domain.enums import EventStatus
from app.domain.exceptions import EventNotFoundError
from app.domain.rules import ensure_transition_allowed
from app.repositories.interfaces import EventRepository


def open_sales(repo: EventRepository, event_id: str) -> Event:
    event = repo.get(event_id)
    if event is None:
        raise EventNotFoundError(event_id)
    ensure_transition_allowed(event.status, EventStatus.ON_SALE)
    event.status = EventStatus.ON_SALE
    repo.update(event)
    return event
