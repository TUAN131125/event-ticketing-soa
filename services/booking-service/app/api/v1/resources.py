"""Internal Booking resource and query endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, Response, status

from app.api.v1.http_contract import (
    CREATED_WITH_ETAG,
    OK_WITH_ETAG,
    booking_response,
)
from app.application.service import BookingService
from app.dependencies import get_service
from app.domain.enums import BookingStatus
from app.domain.value_objects import BookingItem, RequestContext
from app.middleware.authentication import require_internal_caller
from app.schemas.requests import CreateBookingRequest
from app.schemas.responses import (
    BookingHistoryEntryResponse,
    BookingHistoryResponse,
    BookingPageResponse,
    BookingResponse,
    ReconciliationPageResponse,
)

router = APIRouter(prefix="/bookings", tags=["bookings"])
customers_router = APIRouter(prefix="/customers", tags=["bookings"])


@router.post(
    "",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createBooking",
    responses=CREATED_WITH_ETAG,
)
def create(
    body: CreateBookingRequest,
    response: Response,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=128
    ),
    context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingResponse:
    booking = service.create(
        context,
        idempotency_key=idempotency_key,
        customer_id=body.customer_id,
        event_id=body.event_id,
        reservation_id=body.reservation_id,
        payment_method=body.payment_method,
        items=tuple(
            BookingItem(
                seat_id=item.seat_id,
                ticket_type=item.ticket_type,
                unit_price=item.unit_price,
            )
            for item in body.items
        ),
        total_amount=body.total_amount,
        currency=body.currency or "",
    )
    return booking_response(booking, response)


@router.get("", response_model=BookingPageResponse, operation_id="listBookings")
def list_all(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    customer_id: str | None = Query(default=None, alias="customerId"),
    event_id: str | None = Query(default=None, alias="eventId"),
    booking_status: BookingStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, min_length=1, max_length=128),
    _context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingPageResponse:
    return BookingPageResponse.from_page(
        service.list(
            page=page,
            page_size=page_size,
            customer_id=customer_id,
            event_id=event_id,
            status=booking_status,
            search=search,
        )
    )


@router.get(
    "/reconciliation",
    response_model=ReconciliationPageResponse,
    operation_id="reconcileBookings",
)
def reconcile(
    older_than_seconds: int = Query(default=900, alias="olderThanSeconds", ge=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    _context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> ReconciliationPageResponse:
    return ReconciliationPageResponse.from_page(
        service.reconcile(
            older_than_seconds=older_than_seconds, page=page, page_size=page_size
        )
    )


@router.get(
    "/{booking_id}/history",
    response_model=BookingHistoryResponse,
    operation_id="getBookingHistory",
)
def history(
    booking_id: str,
    _context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingHistoryResponse:
    return BookingHistoryResponse(
        bookingId=booking_id,
        items=[
            BookingHistoryEntryResponse.from_value(value)
            for value in service.history(booking_id)
        ],
    )


@router.get(
    "/{booking_id}",
    response_model=BookingResponse,
    operation_id="getBooking",
    responses=OK_WITH_ETAG,
)
def get(
    booking_id: str,
    response: Response,
    _context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingResponse:
    return booking_response(service.get(booking_id), response)


@customers_router.get(
    "/{customer_id}/bookings",
    response_model=BookingPageResponse,
    operation_id="listCustomerBookings",
)
def list_for_customer(
    customer_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    _context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingPageResponse:
    return BookingPageResponse.from_page(
        service.list_for_customer(
            customer_id=customer_id, page=page, page_size=page_size
        )
    )
