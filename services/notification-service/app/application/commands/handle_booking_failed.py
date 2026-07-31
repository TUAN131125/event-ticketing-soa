"""Use case: xu ly webhook booking.failed tu ESB - gui email bao dat ve
khong thanh cong, chong gui trung neu ESB retry cung correlationId."""
from app.domain.entities import Delivery
from app.domain.enums import NotificationType
from app.domain.exceptions import DuplicateCorrelationError
from app.domain.rules import ensure_correlation_not_duplicate
from app.infrastructure.templates.renderer import render
from app.providers.email_provider import EmailProvider
from app.repositories.interfaces import DeliveryRepository

SUBJECT = "Dat ve khong thanh cong"


def handle_booking_failed(
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
        "booking_failed.html",
        booking_id=payload["bookingId"],
        reason=payload.get("reason", ""),
    )

    delivery = Delivery.create(
        repo.next_id(), NotificationType.BOOKING_FAILED, correlation_id, to_email, SUBJECT, body
    )
    try:
        repo.add(delivery)
    except DuplicateCorrelationError:
        return "DUPLICATE_IGNORED"

    provider.send(to=to_email, subject=SUBJECT, body=body)
    return "SENT"
