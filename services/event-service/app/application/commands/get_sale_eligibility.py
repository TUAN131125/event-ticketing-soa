"""EVT-10: ESB goi truoc khi cho phep booking - tra ket qua chi tiet kem
priceSnapshot (gia authoritative, khong lay gia tu UI - invariant #2)."""

from datetime import UTC, datetime

from app.application.commands.get_event import get_event
from app.domain.rules import compute_sale_eligibility
from app.repositories.interfaces import EventRepository


def get_sale_eligibility(repo: EventRepository, event_id: str) -> dict:
    event = get_event(repo, event_id)
    now = datetime.now(UTC)
    eligible, reason_code = compute_sale_eligibility(
        event.status, event.sale_starts_at, event.sale_ends_at, now
    )
    return {
        "event": event,
        "eligible": eligible,
        "reasonCode": reason_code,
    }
