"""EVT-08: Tam dung ban - chuyen ON_SALE sang PAUSED (ngan booking moi)."""

from app.application.commands.get_event import get_event
from app.domain.entities import Event
from app.domain.enums import EventStatus
from app.domain.rules import ensure_transition_allowed
from app.repositories.interfaces import AuditRepository, EventRepository


def pause_event(
    repo: EventRepository,
    audit_repo: AuditRepository,
    actor_id: str,
    event_id: str,
    expected_version: int,
) -> Event:
    event = get_event(repo, event_id)
    ensure_transition_allowed(event.status, EventStatus.PAUSED)
    event.transition_to(EventStatus.PAUSED)
    updated = repo.update(event, expected_version)
    audit_repo.record(event_id, actor_id, "EVT-08:PAUSE")
    return updated
