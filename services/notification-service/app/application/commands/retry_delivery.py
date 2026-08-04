"""Use case: NOT-05 RetryDelivery + NOT-08 ReplayDelivery.

Hop dong (Giai doan 5) chi dinh nghia 1 endpoint POST /deliveries/{id}/retry
- mo hinh nay coi NOT-08 (Admin gui lai co kiem soat) la truong hop dung
cua chinh thao tac retry thu cong nay: Admin/Ops chu dong goi lai khi
delivery dang RETRY_PENDING (tu dong that bai truoc do) hoac DEAD_LETTER
(da vuot nguong, can can thiep tay)."""
from __future__ import annotations

from app.application.commands._send import attempt_send
from app.application.services.event_dispatch import dispatch
from app.domain.entities import Delivery
from app.domain.exceptions import DeliveryNotFoundError
from app.domain.rules import ensure_delivery_retryable
from app.providers.email_provider import EmailProvider
from app.repositories.interfaces import EventDeliveryRepository, TemplateRepository


def retry_delivery(
    event_repo: EventDeliveryRepository,
    template_repo: TemplateRepository,
    provider: EmailProvider,
    delivery_id: str,
) -> Delivery:
    delivery = event_repo.get_delivery(delivery_id)
    if delivery is None:
        raise DeliveryNotFoundError(delivery_id)

    ensure_delivery_retryable(delivery)

    # inbound_events.payload van con nguyen du lieu goc (destination,
    # field can de dien template) - deliveries chi luu destination_hash
    # (khong luu lai email that) nen phai doc lai tu su kien goc de gui
    # lai (xem infrastructure/hashing.py va Muc 4.2 dac ta).
    event = event_repo.get_event(delivery.event_id)
    assert event is not None, "Delivery luon di kem 1 InboundEvent hop le"
    dispatch_result = dispatch(event.event_type.value, event.payload)

    return attempt_send(event_repo, template_repo, provider, delivery, dispatch_result)
