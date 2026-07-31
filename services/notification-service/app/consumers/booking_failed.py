"""Xu ly sau khi nhan webhook booking.failed tu ESB."""
from app.delivery.deduplication import DeduplicationStore
from app.providers.email_provider import EmailProvider
from app.repositories.interfaces import DeliveryLogRepository

TEMPLATE_PATH = "app/templates/booking_failed.html"


def _load_template() -> str:
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        return f.read()


def handle_booking_failed(
    payload: dict,
    provider: EmailProvider,
    dedup: DeduplicationStore,
    delivery_log: DeliveryLogRepository,
) -> str:
    correlation_id = payload["correlationId"]
    if dedup.is_duplicate(correlation_id):
        return "DUPLICATE_IGNORED"

    dedup.mark_processed(correlation_id)
    body = _load_template().format(
        booking_id=payload["bookingId"], reason=payload.get("reason", "")
    )
    email = payload.get("customerEmail", "unknown")
    provider.send(to=email, subject="Dat ve khong thanh cong", body=body)
    delivery_log.add({"type": "booking.failed", **payload})
    return "SENT"
