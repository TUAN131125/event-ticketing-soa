"""EVT-07: Mo ban - chuyen DRAFT/PAUSED sang ON_SALE."""

from app.application.commands.get_event import get_event
from app.domain.entities import Event
from app.domain.enums import EventStatus
from app.domain.rules import ensure_transition_allowed
from app.repositories.interfaces import AuditRepository, EventRepository


def publish_event(
    repo: EventRepository,
    audit_repo: AuditRepository,
    actor_id: str,
    event_id: str,
    expected_version: int,
) -> Event:
    event = get_event(repo, event_id)
    ensure_transition_allowed(event.status, EventStatus.ON_SALE)
    event.transition_to(EventStatus.ON_SALE)
    updated = repo.update(event, expected_version)
    audit_repo.record(event_id, actor_id, "EVT-07:PUBLISH")
    return updated
