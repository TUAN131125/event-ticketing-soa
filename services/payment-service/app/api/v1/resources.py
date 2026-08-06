"""Internal payment resource and query endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.api.http import set_etag
from app.application.service import PaymentService
from app.dependencies import get_service
from app.domain.enums import PaymentStatus
from app.domain.value_objects import BookingPaymentEvidence, RequestContext
from app.middleware.authentication import require_internal_caller
from app.schemas.requests import CreatePaymentRequest
from app.schemas.responses import (
    PaymentPageResponse,
    PaymentResponse,
    ProviderEventListResponse,
    ProviderEventResponse,
    RefundListResponse,
    RefundResponse,
)

router = APIRouter(prefix="/payments", tags=["payments"])

IdempotencyKeyHeader = Annotated[
    str, Header(alias="Idempotency-Key", min_length=1, max_length=128)
]


@router.post(
    "",
    response_model=PaymentResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createPayment",
)
def create(
    response: Response,
    body: CreatePaymentRequest,
    idempotency_key: IdempotencyKeyHeader,
    context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    evidence = None
    if body.booking_evidence is not None:
        value = body.booking_evidence
        evidence = BookingPaymentEvidence.from_request(
            booking_id=value.booking_id,
            customer_id=value.customer_id,
            amount=value.resolved_amount(),
            currency=value.currency,
            resource_version=value.resource_version,
            evidence_id=value.evidence_id,
        )
    payment = service.create(
        context,
        idempotency_key=idempotency_key,
        booking_id=body.booking_id,
        customer_id=body.customer_id,
        amount=body.resolved_amount(),
        currency=body.currency,
        payment_method=body.resolved_payment_method(),
        provider=body.provider,
        method_token=body.method_token,
        booking_evidence=evidence,
    )
    set_etag(response, payment.resource_version)
    return PaymentResponse.from_entity(payment)


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
    response: Response,
    _context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> PaymentResponse:
    payment = service.get(payment_id)
    set_etag(response, payment.resource_version)
    return PaymentResponse.from_entity(payment)


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


@router.get(
    "/{payment_id}/provider-events",
    response_model=ProviderEventListResponse,
    operation_id="listPaymentProviderEvents",
)
def provider_events(
    payment_id: str,
    _context: RequestContext = Depends(require_internal_caller),
    service: PaymentService = Depends(get_service),
) -> ProviderEventListResponse:
    return ProviderEventListResponse(
        items=[
            ProviderEventResponse.from_value(item)
            for item in service.provider_events(payment_id)
        ]
    )
