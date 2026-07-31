"""Xu ly sau khi nhan webhook booking.confirmed tu ESB."""
from app.delivery.deduplication import DeduplicationStore
from app.providers.email_provider import EmailProvider
from app.repositories.interfaces import DeliveryLogRepository

TEMPLATE_PATH = "app/templates/booking_confirmed.html"


def _load_template() -> str:
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        return f.read()


def handle_booking_confirmed(
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
        customer_name=payload.get("customerEmail", ""),
        booking_id=payload["bookingId"],
        ticket_ids=", ".join(payload.get("ticketIds", [])),
    )
    provider.send(to=payload["customerEmail"], subject="Dat ve thanh cong", body=body)
    delivery_log.add({"type": "booking.confirmed", **payload})
    return "SENT"
