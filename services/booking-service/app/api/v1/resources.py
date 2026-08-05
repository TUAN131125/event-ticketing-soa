"""Canonical Booking resource and customer-history endpoints."""

from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Response, status
from libs.platform_http import etag

from app.application.service import BookingService
from app.dependencies import get_service
from app.domain.value_objects import BookingItem, RequestContext
from app.middleware.authentication import require_internal_caller
from app.schemas.requests import CreateBookingRequest
from app.schemas.responses import BookingResponse

router = APIRouter(tags=["bookings"])


@router.post(
    "/bookings",
    response_model=BookingResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createBooking",
)
def create(
    body: CreateBookingRequest,
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingResponse:
    currencies = {item.unit_price.currency for item in body.items}
    if len(currencies) != 1:
        from app.domain.exceptions import InvalidRequest

        raise InvalidRequest("All booking items must use the same currency")
    booking = service.create(
        context,
        idempotency_key=idempotency_key,
        customer_id=body.customer_id,
        event_id=body.event_id,
        items=tuple(
            BookingItem(
                seat_id=item.seat_id,
                ticket_type_code=item.ticket_type_code,
                unit_price=Decimal(item.unit_price.amount_minor),
            )
            for item in body.items
        ),
        currency=currencies.pop(),
    )
    response.headers["ETag"] = etag(booking.resource_version)
    return BookingResponse.from_entity(booking)


@router.get(
    "/bookings/{bookingId}",
    response_model=BookingResponse,
    operation_id="getBooking",
)
def get(
    booking_id: Annotated[str, Path(alias="bookingId")],
    response: Response,
    context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> BookingResponse:
    booking = service.get(booking_id)
    response.headers["ETag"] = etag(booking.resource_version)
    return BookingResponse.from_entity(booking)


@router.get(
    "/customers/{customerId}/bookings",
    response_model=list[BookingResponse],
    operation_id="listCustomerBookings",
)
def history(
    customer_id: Annotated[str, Path(alias="customerId")],
    context: RequestContext = Depends(require_internal_caller),
    service: BookingService = Depends(get_service),
) -> list[BookingResponse]:
    result = service.list(
        page=1,
        page_size=100,
        customer_id=customer_id,
        event_id=None,
        status=None,
        search=None,
    )
    return [BookingResponse.from_entity(item) for item in result.items]
