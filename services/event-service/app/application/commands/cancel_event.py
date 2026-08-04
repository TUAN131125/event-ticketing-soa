"""EVT-09: Huy su kien - phat sinh trang thai CANCELLED va (theo dac ta)
phat event thay doi cho Notification Service. Publish event thuc te
chua trien khai (chua co message broker/webhook target trong MVP), duoc
ghi lai trong audit de truy vet."""

from app.application.commands.get_event import get_event
from app.domain.entities import Event
from app.domain.enums import EventStatus
from app.domain.rules import ensure_transition_allowed
from app.repositories.interfaces import AuditRepository, EventRepository


def cancel_event(
    repo: EventRepository,
    audit_repo: AuditRepository,
    actor_id: str,
    event_id: str,
    expected_version: int,
    reason: str = "",
) -> Event:
    event = get_event(repo, event_id)
    ensure_transition_allowed(event.status, EventStatus.CANCELLED)
    event.transition_to(EventStatus.CANCELLED)
    updated = repo.update(event, expected_version)
    audit_repo.record(event_id, actor_id, f"EVT-09:CANCEL reason={reason!r}")
    return updated
