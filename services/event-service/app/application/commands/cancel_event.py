"""Use case: huy su kien."""
from app.domain.entities import Event
from app.domain.enums import EventStatus
from app.domain.exceptions import EventNotFoundError
from app.domain.rules import ensure_transition_allowed
from app.repositories.interfaces import EventRepository


def cancel_event(repo: EventRepository, event_id: str) -> Event:
    event = repo.get(event_id)
    if event is None:
        raise EventNotFoundError(event_id)
    ensure_transition_allowed(event.status, EventStatus.CANCELLED)
    event.status = EventStatus.CANCELLED
    repo.update(event)
    return event
