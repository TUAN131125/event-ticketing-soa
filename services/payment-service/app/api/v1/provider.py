"""HMAC-protected provider callback endpoint (PAY-07)."""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response

from app.api.http import set_etag
from app.application.service import PaymentService
from app.dependencies import get_service
from app.domain.exceptions import ProviderSignatureInvalid
from app.domain.value_objects import RequestContext
from app.middleware.correlation_id import current_correlation_id
from app.schemas.common import ErrorEnvelope
from app.schemas.requests import ProviderCallbackRequest
from app.schemas.responses import PaymentResponse
from app.security.provider_callback import verify_callback

router = APIRouter(prefix="/payments", tags=["provider-callback"])

WebhookTimestamp = Annotated[str | None, Header(alias="X-Webhook-Timestamp")]
WebhookSignature = Annotated[str | None, Header(alias="X-Webhook-Signature")]
ProviderTimestamp = Annotated[
    str | None,
    Header(
        alias="X-Provider-Timestamp",
        description="Legacy alias for X-Webhook-Timestamp.",
    ),
]
ProviderSignature = Annotated[
    str | None,
    Header(
        alias="X-Provider-Signature",
        description="Legacy alias for X-Webhook-Signature.",
    ),
]


def _compatible_header(
    canonical: str | None,
    legacy: str | None,
    *,
    name: str,
) -> str | None:
    if canonical is not None and legacy is not None and canonical != legacy:
        raise ProviderSignatureInvalid(f"Conflicting {name} callback headers")
    return canonical or legacy


@router.post(
    "/provider-callback",
    response_model=PaymentResponse,
    operation_id="handleProviderCallback",
    responses={
        401: {
            "model": ErrorEnvelope,
            "description": "Signature or timestamp is invalid.",
        },
        409: {
            "model": ErrorEnvelope,
            "description": "Duplicate event or invalid payment transition.",
        },
    },
)
async def provider_callback(
    request: Request,
    response: Response,
    body: ProviderCallbackRequest,
    webhook_timestamp: WebhookTimestamp = None,
    webhook_signature: WebhookSignature = None,
    provider_timestamp: ProviderTimestamp = None,
    provider_signature: ProviderSignature = None,
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    raw_body = await request.body()
    settings = request.app.state.settings
    timestamp = _compatible_header(
        webhook_timestamp,
        provider_timestamp,
        name="timestamp",
    )
    signature = _compatible_header(
        webhook_signature,
        provider_signature,
        name="signature",
    )
    verify_callback(
        secret=settings.provider_callback_secret,
        timestamp=timestamp,
        signature=signature,
        body=raw_body,
        replay_window_seconds=settings.provider_callback_replay_window_seconds,
        max_body_bytes=settings.provider_callback_max_body_bytes,
    )
    payment = service.provider_callback(
        RequestContext(
            correlation_id=current_correlation_id(),
            caller_service=f"provider:{body.provider}",
        ),
        event_id=body.event_id,
        payment_id=body.payment_id,
        provider=body.provider,
        operation=body.operation,
        provider_status=body.provider_status,
        provider_reference=body.provider_reference,
        provider_refund_reference=body.provider_refund_reference,
        amount=body.resolved_amount(),
        currency=body.currency,
        observed_refunded_amount=body.observed_refunded_amount,
        failure_code=body.failure_code,
        reason=body.reason,
        occurred_at=body.occurred_at,
        payload_hash=hashlib.sha256(raw_body).hexdigest(),
    )
    set_etag(response, payment.resource_version)
    return PaymentResponse.from_entity(payment)
