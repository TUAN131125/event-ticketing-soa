"""Internal payment resource and query endpoints."""

from fastapi import APIRouter, Depends, Header, Query, status

from app.application.service import PaymentService
from app.dependencies import get_service
from app.domain.enums import PaymentStatus
from app.domain.value_objects import RequestContext
from app.middleware.authentication import require_internal_caller
from app.observability.metrics import COMMAND_TOTAL
from app.schemas.requests import CreatePaymentRequest
from app.schemas.responses import (
    PaymentPageResponse,
    PaymentResponse,
    RefundListResponse,
    RefundResponse,
)

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post(
    "",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createPayment",
)
def create(
    body: CreatePaymentRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=128
    ),
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    try:
        payment = service.create(
            context,
            idempotency_key=idempotency_key,
            booking_id=body.booking_id,
            customer_id=body.customer_id,
            amount=body.amount,
            currency=body.currency,
            payment_method=body.payment_method,
            provider=body.provider,
        )
        COMMAND_TOTAL.labels("create", "success").inc()
        return PaymentResponse.from_entity(payment)
    except Exception:
        COMMAND_TOTAL.labels("create", "failure").inc()
        raise


@router.get("", response_model=PaymentPageResponse, operation_id="listPayments")
def list_all(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    booking_id: str | None = Query(default=None, alias="bookingId"),
    customer_id: str | None = Query(default=None, alias="customerId"),
    provider: str | None = Query(default=None, min_length=1, max_length=40),
    payment_status: PaymentStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, min_length=1, max_length=128),
    _context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentPageResponse:
    return PaymentPageResponse.from_page(
        service.list(
            page=page,
            page_size=page_size,
            booking_id=booking_id,
            customer_id=customer_id,
            provider=provider,
            status=payment_status,
            search=search,
        )
    )


@router.get("/{payment_id}", response_model=PaymentResponse, operation_id="getPayment")
def get(
    payment_id: str,
    _context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    return PaymentResponse.from_entity(service.get(payment_id))


@router.get(
    "/{payment_id}/refunds",
    response_model=RefundListResponse,
    operation_id="listPaymentRefunds",
)
def refunds(
    payment_id: str,
    _context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> RefundListResponse:
    return RefundListResponse(
        items=[RefundResponse.from_value(item) for item in service.refunds(payment_id)]
    )
