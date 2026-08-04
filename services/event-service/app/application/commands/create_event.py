"""EVT-01: Admin tao ban nhap su kien (DRAFT)."""

from datetime import datetime

from app.domain.entities import Event
from app.domain.rules import validate_event_dates
from app.domain.value_objects import TicketType
from app.repositories.interfaces import AuditRepository, EventRepository


def create_event(
    repo: EventRepository,
    audit_repo: AuditRepository,
    actor_id: str,
    name: str,
    venue: str,
    starts_at: datetime,
    sale_starts_at: datetime,
    sale_ends_at: datetime,
    ticket_types: list[TicketType],
) -> Event:
    validate_event_dates(starts_at, sale_starts_at, sale_ends_at)
    event = Event.create(
        repo.next_id(),
        name,
        venue,
        starts_at,
        sale_starts_at,
        sale_ends_at,
        ticket_types,
    )
    repo.add(event)
    audit_repo.record(event.id, actor_id, "EVT-01:CREATE")
    return event
