"""Use case: xu ly webhook booking.confirmed tu ESB - gui email xac nhan
dat ve thanh cong, chong gui trung neu ESB retry cung correlationId."""

from app.domain.entities import Delivery
from app.domain.enums import NotificationType
from app.domain.exceptions import DuplicateCorrelationError
from app.domain.rules import ensure_correlation_not_duplicate
from app.infrastructure.templates.renderer import render
from app.providers.email_provider import EmailProvider
from app.repositories.interfaces import DeliveryRepository

SUBJECT = "Dat ve thanh cong"


def handle_booking_confirmed(
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

    to_email = payload.get("customerEmail", "")
    body = render(
        "booking_confirmed.html",
        customer_name=to_email,
        booking_id=payload["bookingId"],
        ticket_ids=", ".join(payload.get("ticketIds", [])),
    )

    delivery = Delivery.create(
        repo.next_id(),
        NotificationType.BOOKING_CONFIRMED,
        correlation_id,
        to_email,
        SUBJECT,
        body,
    )
    try:
        repo.add(delivery)
    except DuplicateCorrelationError:
        # Rui ro rat nho: 2 webhook cung correlationId toi gan nhu dong
        # thoi, ca 2 deu vuot qua kiem tra o tren truoc khi insert. UNIQUE
        # constraint chan ban ghi thu 2, coi nhu retry - khong gui email
        # lan nua.
        return "DUPLICATE_IGNORED"

    provider.send(to=to_email, subject=SUBJECT, body=body)
    return "SENT"
