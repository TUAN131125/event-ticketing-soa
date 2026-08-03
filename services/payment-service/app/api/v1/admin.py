"""Provider-outcome and compensating payment commands."""

from fastapi import APIRouter, Depends, Header

from app.application.service import PaymentService
from app.dependencies import get_service
from app.domain.value_objects import RequestContext
from app.middleware.authentication import require_internal_caller
from app.observability.metrics import COMMAND_TOTAL
from app.schemas.requests import (
    AuthorizePaymentRequest,
    CancelPaymentRequest,
    CapturePaymentRequest,
    ReconcilePaymentRequest,
    RefundPaymentRequest,
)
from app.schemas.responses import PaymentResponse

router = APIRouter(prefix="/payments", tags=["payment-commands"])


@router.post(
    "/{payment_id}/authorize",
    response_model=PaymentResponse,
    operation_id="authorizePayment",
)
def authorize(
    payment_id: str,
    body: AuthorizePaymentRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=128
    ),
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    try:
        result = service.authorize(
            context,
            idempotency_key=idempotency_key,
            payment_id=payment_id,
            approved=body.approved,
            provider_reference=body.provider_reference,
            failure_code=body.failure_code,
            reason=body.reason,
            expected_version=body.expected_version,
        )
        COMMAND_TOTAL.labels("authorize", "success").inc()
        return PaymentResponse.from_entity(result)
    except Exception:
        COMMAND_TOTAL.labels("authorize", "failure").inc()
        raise


@router.post(
    "/{payment_id}/capture",
    response_model=PaymentResponse,
    operation_id="capturePayment",
)
def capture(
    payment_id: str,
    body: CapturePaymentRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=128
    ),
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    try:
        result = service.capture(
            context,
            idempotency_key=idempotency_key,
            payment_id=payment_id,
            succeeded=body.succeeded,
            provider_reference=body.provider_reference,
            failure_code=body.failure_code,
            reason=body.reason,
            expected_version=body.expected_version,
        )
        COMMAND_TOTAL.labels("capture", "success").inc()
        return PaymentResponse.from_entity(result)
    except Exception:
        COMMAND_TOTAL.labels("capture", "failure").inc()
        raise


@router.post(
    "/{payment_id}/cancel",
    response_model=PaymentResponse,
    operation_id="cancelPayment",
)
def cancel(
    payment_id: str,
    body: CancelPaymentRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=128
    ),
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    try:
        result = service.cancel(
            context,
            idempotency_key=idempotency_key,
            payment_id=payment_id,
            reason=body.reason,
            provider_reference=body.provider_reference,
            expected_version=body.expected_version,
        )
        COMMAND_TOTAL.labels("cancel", "success").inc()
        return PaymentResponse.from_entity(result)
    except Exception:
        COMMAND_TOTAL.labels("cancel", "failure").inc()
        raise


@router.post(
    "/{payment_id}/refund",
    response_model=PaymentResponse,
    operation_id="refundPayment",
)
def refund(
    payment_id: str,
    body: RefundPaymentRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=128
    ),
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    try:
        result = service.refund(
            context,
            idempotency_key=idempotency_key,
            payment_id=payment_id,
            amount=body.amount,
            reason=body.reason,
            provider_refund_reference=body.provider_refund_reference,
            expected_version=body.expected_version,
        )
        COMMAND_TOTAL.labels("refund", "success").inc()
        return PaymentResponse.from_entity(result)
    except Exception:
        COMMAND_TOTAL.labels("refund", "failure").inc()
        raise


@router.post(
    "/{payment_id}/reconcile",
    response_model=PaymentResponse,
    operation_id="reconcilePayment",
)
def reconcile(
    payment_id: str,
    body: ReconcilePaymentRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=128
    ),
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    try:
        result = service.reconcile(
            context,
            idempotency_key=idempotency_key,
            payment_id=payment_id,
            provider_status=body.provider_status,
            provider_reference=body.provider_reference,
            provider_refund_reference=body.provider_refund_reference,
            observed_refunded_amount=body.observed_refunded_amount,
            failure_code=body.failure_code,
            reason=body.reason,
            expected_version=body.expected_version,
        )
        COMMAND_TOTAL.labels("reconcile", "success").inc()
        return PaymentResponse.from_entity(result)
    except Exception:
        COMMAND_TOTAL.labels("reconcile", "failure").inc()
        raise
