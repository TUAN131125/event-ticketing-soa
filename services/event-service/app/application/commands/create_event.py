"""Use case: create a canonical draft event."""

from datetime import datetime

from app.domain.entities import Event
from app.domain.value_objects import TicketType
from app.repositories.interfaces import EventRepository


def create_event(
    repo: EventRepository,
    name: str,
    venue: str,
    starts_at: datetime,
    sale_starts_at: datetime,
    sale_ends_at: datetime,
    ticket_types: list[TicketType],
) -> Event:
    event_id = repo.next_id()
    event = Event.create(
        event_id,
        name,
        venue,
        starts_at,
        sale_starts_at,
        sale_ends_at,
        ticket_types,
    )
    repo.add(event)
    return event
