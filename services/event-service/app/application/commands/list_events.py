"""Use case: liet ke tat ca su kien."""

from collections.abc import Iterable

from app.domain.entities import Event
from app.repositories.interfaces import EventRepository


def list_events(repo: EventRepository) -> Iterable[Event]:
    return repo.list_all()
