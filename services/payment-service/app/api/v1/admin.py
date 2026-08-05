"""Canonical Payment commands using the local provider boundary."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Response, status
from libs.platform_http import etag, parse_if_match

from app.application.service import PaymentService
from app.dependencies import get_service
from app.domain.exceptions import PaymentDeclined
from app.domain.value_objects import RequestContext
from app.middleware.authentication import require_internal_caller
from app.schemas.requests import RefundPaymentRequest
from app.schemas.responses import PaymentResponse, RefundResponse

router = APIRouter(prefix="/payments", tags=["payment-commands"])


def _provider_reference(payment_id: str, action: str) -> str:
    return f"{action}-{payment_id}"


def _headers(
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    if_match: Annotated[str, Header(alias="If-Match", pattern=r'^"[1-9][0-9]*"$')],
) -> tuple[str, int]:
    return idempotency_key, parse_if_match(if_match)


@router.post(
    "/{paymentId}/authorize",
    response_model=PaymentResponse,
    operation_id="authorizePayment",
)
def authorize(
    payment_id: Annotated[str, Path(alias="paymentId")],
    response: Response,
    headers: tuple[str, int] = Depends(_headers),
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    current = service.get(payment_id)
    approved = not current.payment_method.lower().startswith("decline")
    payment = service.authorize(
        context,
        idempotency_key=headers[0],
        payment_id=payment_id,
        approved=approved,
        provider_reference=_provider_reference(payment_id, "auth")
        if approved
        else None,
        failure_code=None if approved else "DECLINED",
        reason=None if approved else "Provider declined the payment",
        expected_version=headers[1],
    )
    if not approved:
        raise PaymentDeclined()
    response.headers["ETag"] = etag(payment.resource_version)
    return PaymentResponse.from_entity(payment)


@router.post(
    "/{paymentId}/capture",
    response_model=PaymentResponse,
    operation_id="capturePayment",
)
def capture(
    payment_id: Annotated[str, Path(alias="paymentId")],
    response: Response,
    headers: tuple[str, int] = Depends(_headers),
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    payment = service.capture(
        context,
        idempotency_key=headers[0],
        payment_id=payment_id,
        succeeded=True,
        provider_reference=_provider_reference(payment_id, "auth"),
        failure_code=None,
        reason=None,
        expected_version=headers[1],
    )
    response.headers["ETag"] = etag(payment.resource_version)
    return PaymentResponse.from_entity(payment)


@router.post(
    "/{paymentId}/cancel", response_model=PaymentResponse, operation_id="cancelPayment"
)
def cancel(
    payment_id: Annotated[str, Path(alias="paymentId")],
    response: Response,
    headers: tuple[str, int] = Depends(_headers),
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    payment = service.cancel(
        context,
        idempotency_key=headers[0],
        payment_id=payment_id,
        reason="Booking workflow cancelled",
        provider_reference=None,
        expected_version=headers[1],
    )
    response.headers["ETag"] = etag(payment.resource_version)
    return PaymentResponse.from_entity(payment)


@router.post(
    "/{paymentId}/refunds",
    response_model=RefundResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createRefund",
)
def refund(
    payment_id: Annotated[str, Path(alias="paymentId")],
    body: RefundPaymentRequest,
    headers: tuple[str, int] = Depends(_headers),
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> RefundResponse:
    service.refund(
        context,
        idempotency_key=headers[0],
        payment_id=payment_id,
        amount=Decimal(body.amount.amount_minor),
        reason=body.reason,
        provider_refund_reference=_provider_reference(
            payment_id, f"refund-{headers[1]}"
        ),
        expected_version=headers[1],
    )
    refunds = service.refunds(payment_id)
    return RefundResponse.from_value(refunds[-1])


@router.post(
    "/{paymentId}/reconcile",
    response_model=PaymentResponse,
    operation_id="reconcilePayment",
)
def reconcile(
    payment_id: Annotated[str, Path(alias="paymentId")],
    response: Response,
    headers: tuple[str, int] = Depends(_headers),
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    payment = service.get(payment_id)
    if payment.resource_version != headers[1]:
        from app.domain.exceptions import VersionConflict

        raise VersionConflict(headers[1], payment.resource_version)
    response.headers["ETag"] = etag(payment.resource_version)
    return PaymentResponse.from_entity(payment)
