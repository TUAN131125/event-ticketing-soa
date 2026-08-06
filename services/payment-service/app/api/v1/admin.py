"""Payment state commands, including compatibility and canonical refund routes."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response

from app.api.http import resolve_expected_version, set_etag
from app.application.service import PaymentService
from app.dependencies import get_service
from app.domain.enums import PaymentStatus
from app.domain.exceptions import InvalidRequest, PaymentDeclined
from app.domain.value_objects import RequestContext
from app.middleware.authentication import require_internal_caller
from app.schemas.requests import (
    AuthorizePaymentRequest,
    CancelPaymentRequest,
    CapturePaymentRequest,
    ReconcilePaymentRequest,
    RefundPaymentRequest,
)
from app.schemas.common import ErrorEnvelope
from app.schemas.responses import PaymentResponse

router = APIRouter(prefix="/payments", tags=["payment-commands"])

IdempotencyKeyHeader = Annotated[
    str, Header(alias="Idempotency-Key", min_length=1, max_length=128)
]
IfMatchHeader = Annotated[str | None, Header(alias="If-Match")]


def _response(
    response: Response,
    payment,
    *,
    canonical_decline: bool = False,
) -> PaymentResponse:
    set_etag(response, payment.resource_version)
    if payment.status == PaymentStatus.UNKNOWN:
        response.status_code = 202
    if canonical_decline and payment.status == PaymentStatus.FAILED:
        raise PaymentDeclined(
            payment.payment_id,
            payment.failure_reason or "Provider declined the payment",
        )
    return PaymentResponse.from_entity(payment)


@router.post(
    "/{payment_id}/authorize",
    response_model=PaymentResponse,
    operation_id="authorizePayment",
    responses={
        202: {"model": PaymentResponse, "description": "Provider outcome is UNKNOWN."},
        402: {"model": ErrorEnvelope, "description": "Provider declined the payment."},
        409: {
            "model": ErrorEnvelope,
            "description": "State, version or idempotency conflict.",
        },
    },
)
def authorize(
    payment_id: str,
    body: AuthorizePaymentRequest,
    response: Response,
    idempotency_key: IdempotencyKeyHeader,
    if_match: IfMatchHeader = None,
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    payment = service.authorize(
        context,
        idempotency_key=idempotency_key,
        payment_id=payment_id,
        approved=body.approved,
        provider_status=body.provider_status,
        provider_reference=body.provider_reference,
        failure_code=body.failure_code,
        reason=body.reason,
        expected_version=resolve_expected_version(body.expected_version, if_match),
    )
    return _response(
        response,
        payment,
        canonical_decline=body.approved is None,
    )


@router.post(
    "/{payment_id}/capture",
    response_model=PaymentResponse,
    operation_id="capturePayment",
    responses={
        202: {"model": PaymentResponse, "description": "Provider outcome is UNKNOWN."},
        402: {"model": ErrorEnvelope, "description": "Provider declined capture."},
        409: {
            "model": ErrorEnvelope,
            "description": "State, version or idempotency conflict.",
        },
    },
)
def capture(
    payment_id: str,
    body: CapturePaymentRequest,
    response: Response,
    idempotency_key: IdempotencyKeyHeader,
    if_match: IfMatchHeader = None,
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    payment = service.capture(
        context,
        idempotency_key=idempotency_key,
        payment_id=payment_id,
        succeeded=body.succeeded,
        provider_status=body.provider_status,
        provider_reference=body.provider_reference,
        failure_code=body.failure_code,
        reason=body.reason,
        expected_version=resolve_expected_version(body.expected_version, if_match),
    )
    return _response(
        response,
        payment,
        canonical_decline=body.succeeded is None,
    )


@router.post(
    "/{payment_id}/cancel",
    response_model=PaymentResponse,
    operation_id="cancelPayment",
)
def cancel(
    payment_id: str,
    body: CancelPaymentRequest,
    response: Response,
    idempotency_key: IdempotencyKeyHeader,
    if_match: IfMatchHeader = None,
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    payment = service.cancel(
        context,
        idempotency_key=idempotency_key,
        payment_id=payment_id,
        reason=body.reason,
        provider_reference=body.provider_reference,
        provider_status=body.provider_status,
        expected_version=resolve_expected_version(body.expected_version, if_match),
    )
    return _response(response, payment)


def _refund(
    payment_id: str,
    body: RefundPaymentRequest,
    response: Response,
    idempotency_key: str,
    if_match: str | None,
    context: RequestContext,
    service: PaymentService,
) -> PaymentResponse:
    current = service.get(payment_id)
    try:
        amount: Decimal = body.resolved_amount(current.currency)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc
    payment = service.refund(
        context,
        idempotency_key=idempotency_key,
        payment_id=payment_id,
        amount=amount,
        reason=body.reason,
        provider_refund_reference=body.provider_refund_reference,
        provider_status=body.provider_status,
        expected_version=resolve_expected_version(body.expected_version, if_match),
    )
    return _response(response, payment)


@router.post(
    "/{payment_id}/refund",
    response_model=PaymentResponse,
    operation_id="refundPayment",
    description="Legacy path retained for existing ESB consumers.",
)
def refund_legacy(
    payment_id: str,
    body: RefundPaymentRequest,
    response: Response,
    idempotency_key: IdempotencyKeyHeader,
    if_match: IfMatchHeader = None,
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    return _refund(
        payment_id,
        body,
        response,
        idempotency_key,
        if_match,
        context,
        service,
    )


@router.post(
    "/{payment_id}/refunds",
    response_model=PaymentResponse,
    operation_id="createPaymentRefund",
    description="Canonical Stage 3/5 refund command path.",
)
def refund_canonical(
    payment_id: str,
    body: RefundPaymentRequest,
    response: Response,
    idempotency_key: IdempotencyKeyHeader,
    if_match: IfMatchHeader = None,
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    return _refund(
        payment_id,
        body,
        response,
        idempotency_key,
        if_match,
        context,
        service,
    )


@router.post(
    "/{payment_id}/reconcile",
    response_model=PaymentResponse,
    operation_id="reconcilePayment",
    responses={
        409: {
            "model": ErrorEnvelope,
            "description": "State, version or idempotency conflict.",
        },
        503: {
            "model": ErrorEnvelope,
            "description": "Provider outcome is unavailable; retry after backoff.",
        },
    },
)
def reconcile(
    payment_id: str,
    body: ReconcilePaymentRequest,
    response: Response,
    idempotency_key: IdempotencyKeyHeader,
    if_match: IfMatchHeader = None,
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    payment = service.reconcile(
        context,
        idempotency_key=idempotency_key,
        payment_id=payment_id,
        provider_status=body.provider_status,
        provider_reference=body.provider_reference,
        provider_refund_reference=body.provider_refund_reference,
        observed_refunded_amount=body.observed_refunded_amount,
        failure_code=body.failure_code,
        reason=body.reason,
        expected_version=resolve_expected_version(body.expected_version, if_match),
    )
    return _response(response, payment)
