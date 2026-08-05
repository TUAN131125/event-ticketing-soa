"""Generic signed canonical Notification webhook ingress."""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.dependencies import get_provider, get_repository
from app.domain.entities import Delivery
from app.domain.enums import DeliveryStatus
from app.middleware.authentication import require_webhook_hmac
from app.providers.email_provider import EmailProvider
from app.repositories.interfaces import DeliveryRepository
from app.schemas.requests import EventEnvelopeRequest

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _content(payload: EventEnvelopeRequest) -> tuple[str, str, str]:
    recipient = str(payload.data.get("customerEmail", ""))
    subject = {
        "booking.confirmed": "Booking confirmed",
        "booking.failed": "Booking failed",
        "event.changed": "Event changed",
        "ticket.issued": "Ticket issued",
    }[payload.event_type]
    return recipient, subject, str(payload.data)


@router.post(
    "/events",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="receiveEventWebhook",
    dependencies=[Depends(require_webhook_hmac)],
    openapi_extra={
        "parameters": [
            {
                "name": "X-Webhook-Timestamp",
                "in": "header",
                "required": True,
                "schema": {
                    "type": "string",
                    "format": "date-time",
                    "pattern": r"(?:Z|\+00:00)$",
                },
            }
        ]
    },
)
def receive_event(
    payload: EventEnvelopeRequest,
    repo: DeliveryRepository = Depends(get_repository),
    provider: EmailProvider = Depends(get_provider),
) -> Response:
    if repo.get_by_event_id(payload.event_id) is not None:
        raise HTTPException(
            status_code=409, detail="Webhook event was already accepted"
        )
    recipient, subject, body = _content(payload)
    delivery = Delivery.create(
        repo.next_id(), payload.event_id, recipient, subject, body
    )
    repo.add(delivery)
    delivery.attempt_count = 1
    try:
        provider.send(to=recipient, subject=subject, body=body)
        delivery.status = DeliveryStatus.DELIVERED
    except Exception:  # noqa: BLE001 -- delivery failure is persisted for retry
        delivery.status = DeliveryStatus.RETRY_PENDING
        delivery.last_error_code = "PROVIDER_FAILURE"
    delivery.resource_version += 1
    repo.update(delivery)
    return Response(status_code=status.HTTP_202_ACCEPTED)
