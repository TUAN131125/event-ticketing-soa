"""Use case: xu ly su kien EVENT_CHANGED (EVT-12).

Chua co endpoint webhook goi toi trong MVP - Event Service chua publish
su kien nay (chi moi co state machine DRAFT/ON_SALE/PAUSED/CLOSED/
CANCELLED, chua co co che publish qua ESB). Giu lai lam diem mo rong: khi
Event Service san sang publish, chi can them 1 route trong
api/v1/webhooks.py goi ham nay, khong can sua gi them o day.
"""

from app.domain.entities import Delivery
from app.domain.enums import NotificationType
from app.domain.exceptions import DuplicateCorrelationError
from app.domain.rules import ensure_correlation_not_duplicate
from app.infrastructure.templates.renderer import render
from app.providers.email_provider import EmailProvider
from app.repositories.interfaces import DeliveryRepository

SUBJECT = "Su kien thay doi"


def handle_event_changed(
    repo: DeliveryRepository,
    provider: EmailProvider,
    payload: dict,
) -> str:
    correlation_id = payload["correlationId"]
    try:
        ensure_correlation_not_duplicate(
            repo.exists_by_correlation_id(correlation_id), correlation_id
        )
    except DuplicateCorrelationError:
        return "DUPLICATE_IGNORED"

    to_email = payload.get("customerEmail") or "unknown"
    body = render(
        "event_changed.html",
        event_id=payload.get("eventId", ""),
        change_summary=payload.get("changeSummary", ""),
    )

    delivery = Delivery.create(
        repo.next_id(),
        NotificationType.EVENT_CHANGED,
        correlation_id,
        to_email,
        SUBJECT,
        body,
    )
    try:
        repo.add(delivery)
    except DuplicateCorrelationError:
        return "DUPLICATE_IGNORED"

    provider.send(to=to_email, subject=SUBJECT, body=body)
    return "SENT"
