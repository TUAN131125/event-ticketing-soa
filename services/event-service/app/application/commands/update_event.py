"""Use case: cap nhat thong tin su kien (khong doi trang thai)."""

from app.domain.entities import Event
from app.domain.exceptions import EventNotFoundError
from app.repositories.interfaces import EventRepository


def update_event(repo: EventRepository, event_id: str, name: str | None = None,
                  location: str | None = None, start_time: str | None = None) -> Event:
    event = repo.get(event_id)
    if event is None:
        raise EventNotFoundError(event_id)
    event.update_info(name=name, location=location, start_time=start_time)
    repo.update(event)
    return event
