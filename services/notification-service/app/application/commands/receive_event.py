"""Use case: NOT-01 ReceiveEvent + NOT-02 ValidateEvent + NOT-03
CreateDelivery + NOT-04 SendEmail - nhan 1 EventEnvelope da qua xac thuc
chu ky (security/webhook_signature.py, chay o tang API truoc khi toi day),
kiem tra eventId chua tung xu ly, tao delivery va gui ngay (dong bo -
chua co scheduler/queue nen khong the gui "nen" bat dong bo that su
trong MVP nay)."""
from __future__ import annotations

from typing import Any

from app.application.commands._send import attempt_send
from app.application.services.event_dispatch import dispatch
from app.domain.entities import Delivery, InboundEvent
from app.domain.enums import Channel, EventType
from app.domain.exceptions import DuplicateEventError
from app.domain.rules import ensure_event_not_duplicate
from app.infrastructure.hashing import hash_destination
from app.providers.email_provider import EmailProvider
from app.repositories.interfaces import EventDeliveryRepository, TemplateRepository


def receive_event(
    event_repo: EventDeliveryRepository,
    template_repo: TemplateRepository,
    provider: EmailProvider,
    envelope: dict[str, Any],
) -> Delivery:
    event_id = envelope["eventId"]

    # NOT-02/eventId idempotency (Muc 4.2): kiem tra o tang application
    # truoc de tra loi nhanh; hang rao cuoi cung la PRIMARY KEY event_id
    # trong add_event() (xem infrastructure/database/repositories.py).
    ensure_event_not_duplicate(event_repo.event_exists(event_id), event_id)

    data = envelope["data"]
    # Co the nem EventSchemaInvalidError (422) neu thieu field bat buoc
    # trong `data` theo eventType - kiem tra TRUOC khi ghi inbound_events
    # de khong luu su kien khong hop le.
    dispatch_result = dispatch(envelope["eventType"], data)

    inbound_event = InboundEvent.create(
        event_id=event_id,
        event_type=EventType(envelope["eventType"]),
        schema_version=envelope["schemaVersion"],
        correlation_id=envelope["correlationId"],
        aggregate_id=envelope["aggregateId"],
        payload=data,
    )
    try:
        event_repo.add_event(inbound_event)
    except DuplicateEventError:
        # Rui ro rat nho: 2 webhook cung eventId gan nhu dong thoi, ca 2
        # deu vuot qua kiem tra o tren truoc khi insert.
        raise

    delivery = Delivery.create(
        delivery_id=event_repo.next_delivery_id(),
        event_id=event_id,
        channel=Channel.EMAIL,
        destination_hash=hash_destination(dispatch_result.destination),
    )
    event_repo.add_delivery(delivery)

    return attempt_send(event_repo, template_repo, provider, delivery, dispatch_result)
