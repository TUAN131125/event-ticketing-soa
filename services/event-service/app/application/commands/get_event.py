"""EVT-04: Xem chi tiet 1 su kien."""

from app.domain.entities import Event
from app.domain.exceptions import EventNotFoundError
from app.repositories.interfaces import EventRepository


def get_event(repo: EventRepository, event_id: str) -> Event:
    event = repo.get(event_id)
    if event is None:
        raise EventNotFoundError(event_id)
    return event
