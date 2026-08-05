"""Replace canonical Event details with optimistic concurrency."""

from datetime import datetime

from app.domain.entities import Event
from app.domain.exceptions import EventNotFoundError, InvalidStateTransitionError
from app.domain.value_objects import TicketType
from app.repositories.interfaces import EventRepository


def update_event(
    repo: EventRepository,
    event_id: str,
    *,
    name: str,
    venue: str,
    starts_at: datetime,
    sale_starts_at: datetime,
    sale_ends_at: datetime,
    ticket_types: list[TicketType],
    expected_version: int,
) -> Event:
    event = repo.get(event_id)
    if event is None:
        raise EventNotFoundError(event_id)
    if event.resource_version != expected_version:
        raise InvalidStateTransitionError(
            str(event.resource_version), str(expected_version)
        )
    event.replace(
        name=name,
        venue=venue,
        starts_at=starts_at,
        sale_starts_at=sale_starts_at,
        sale_ends_at=sale_ends_at,
        ticket_types=ticket_types,
    )
    repo.update(event)
    return event
