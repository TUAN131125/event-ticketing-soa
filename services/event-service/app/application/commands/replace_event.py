"""EVT-02: PUT /events/{id} - thay the toan bo profile theo
resourceVersion/If-Match (invariant #4 - optimistic concurrency)."""

from datetime import datetime

from app.application.commands.get_event import get_event
from app.domain.entities import Event
from app.domain.rules import validate_event_dates
from app.domain.value_objects import TicketType
from app.repositories.interfaces import AuditRepository, EventRepository


def replace_event(
    repo: EventRepository,
    audit_repo: AuditRepository,
    actor_id: str,
    event_id: str,
    expected_version: int,
    name: str,
    venue: str,
    starts_at: datetime,
    sale_starts_at: datetime,
    sale_ends_at: datetime,
    ticket_types: list[TicketType],
) -> Event:
    event = get_event(repo, event_id)  # 404 neu khong ton tai
    validate_event_dates(starts_at, sale_starts_at, sale_ends_at)
    event.replace_profile(
        name, venue, starts_at, sale_starts_at, sale_ends_at, ticket_types
    )
    updated = repo.update(event, expected_version)  # 409 VERSION_CONFLICT neu sai
    audit_repo.record(event_id, actor_id, "EVT-02:REPLACE")
    return updated
