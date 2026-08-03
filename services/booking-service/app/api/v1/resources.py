"""Internal booking resource and query endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Query, status

from app.application.service import BookingService
from app.dependencies import get_service
from app.domain.enums import BookingStatus
from app.domain.value_objects import BookingItem, RequestContext
from app.middleware.authentication import require_internal_caller
from app.observability.metrics import COMMAND_TOTAL
from app.schemas.requests import CreateBookingRequest
from app.schemas.responses import BookingPageResponse, BookingResponse

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post(
    "",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createBooking",
)
def create(
    body: CreateBookingRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=128
    ),
    context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingResponse:
    try:
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
            currency=body.currency,
        )
        COMMAND_TOTAL.labels("create", "success").inc()
        return BookingResponse.from_entity(booking)
    except Exception:
        COMMAND_TOTAL.labels("create", "failure").inc()
        raise


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
    result = service.list(
        page=page,
        page_size=page_size,
        customer_id=customer_id,
        event_id=event_id,
        status=booking_status,
        search=search,
    )
    return BookingPageResponse.from_page(result)


@router.get("/{booking_id}", response_model=BookingResponse, operation_id="getBooking")
def get(
    booking_id: str,
    _context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingResponse:
    return BookingResponse.from_entity(service.get(booking_id))
