"""Ham dung chung giua receive_event (lan gui dau) va retry_delivery
(gui lai thu cong) - NOT-04 SendEmail + NOT-10 AuditDelivery."""
from __future__ import annotations

from app.application.services.event_dispatch import EventDispatchResult
from app.domain.entities import Delivery, DeliveryAttempt
from app.domain.exceptions import ProviderPermanentError, ProviderTemporaryError
from app.domain.rules import MAX_DELIVERY_ATTEMPTS, RETRY_BACKOFF_BASE_SECONDS
from app.infrastructure.templates.renderer import render
from app.providers.email_provider import EmailProvider
from app.repositories.interfaces import EventDeliveryRepository, TemplateRepository


def attempt_send(
    event_repo: EventDeliveryRepository,
    template_repo: TemplateRepository,
    provider: EmailProvider,
    delivery: Delivery,
    dispatch_result: EventDispatchResult,
) -> Delivery:
    delivery.mark_sending()
    event_repo.update_delivery(delivery)

    subject, body = render(template_repo, dispatch_result.template_code, dispatch_result.template_fields)
    try:
        provider.send(to=dispatch_result.destination, subject=subject, body=body)
    except (ProviderTemporaryError, ProviderPermanentError) as exc:
        delivery.mark_failed(
            exc.code, max_attempts=MAX_DELIVERY_ATTEMPTS, backoff_seconds=RETRY_BACKOFF_BASE_SECONDS
        )
        event_repo.update_delivery(delivery)
        event_repo.add_attempt(
            DeliveryAttempt(delivery.id, delivery.attempt_count, delivery.status, exc.code)
        )
        return delivery

    delivery.mark_delivered()
    event_repo.update_delivery(delivery)
    event_repo.add_attempt(
        DeliveryAttempt(delivery.id, delivery.attempt_count, delivery.status, None)
    )
    return delivery
