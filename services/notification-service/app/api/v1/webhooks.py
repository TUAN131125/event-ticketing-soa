"""NOT-01 ReceiveEvent - endpoint webhook DUY NHAT theo hop dong (Giai
doan 5): POST /webhooks/events, nhan EventEnvelope, tra 202. Khong yeu
cau Bearer JWT (security: [] trong OpenAPI - ESB goi bang chu ky HMAC
rieng, xem security/webhook_signature.py) nhung PHAI co X-Signature hop
le."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, Request
from pydantic import ValidationError

from app.application.commands.receive_event import receive_event
from app.config import Settings, get_settings
from app.dependencies import get_event_repository, get_provider, get_template_repository
from app.domain.exceptions import EventSchemaInvalidError
from app.providers.email_provider import EmailProvider
from app.repositories.interfaces import EventDeliveryRepository, TemplateRepository
from app.schemas.requests import EventEnvelope
from app.security.webhook_signature import SIGNATURE_HEADER, verify_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/events", status_code=202)
async def receive_event_webhook(
    request: Request,
    x_signature: str | None = Header(default=None, alias=SIGNATURE_HEADER),
    settings: Settings = Depends(get_settings),
    event_repo: EventDeliveryRepository = Depends(get_event_repository),
    template_repo: TemplateRepository = Depends(get_template_repository),
    provider: EmailProvider = Depends(get_provider),
):
    raw_body = await request.body()
    # NOT-02: xac minh chu ky TRUOC khi parse/tin bat cu field nao trong
    # body - tranh xu ly payload chua duoc xac thuc nguon goc.
    verify_signature(raw_body, x_signature, settings.webhook_shared_secret)

    try:
        envelope = EventEnvelope.model_validate(json.loads(raw_body))
    except (ValidationError, json.JSONDecodeError) as exc:
        raise EventSchemaInvalidError(f"EventEnvelope khong hop le: {exc}") from exc

    delivery = receive_event(event_repo, template_repo, provider, envelope.model_dump())
    return {"eventId": envelope.eventId, "deliveryId": delivery.id, "status": delivery.status.value}
