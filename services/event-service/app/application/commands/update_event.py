"""Use case: cap nhat thong tin su kien (khong doi trang thai)."""
from typing import Optional

from app.domain.entities import Event
from app.domain.exceptions import EventNotFoundError
from app.repositories.interfaces import EventRepository


def update_event(repo: EventRepository, event_id: str, name: Optional[str] = None,
                  location: Optional[str] = None, start_time: Optional[str] = None) -> Event:
    event = repo.get(event_id)
    if event is None:
        raise EventNotFoundError(event_id)
    event.update_info(name=name, location=location, start_time=start_time)
    repo.update(event)
    return event
