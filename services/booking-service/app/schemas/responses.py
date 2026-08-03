"""Booking response contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import Booking
from app.domain.enums import BookingStatus, PaymentStatus
from app.domain.value_objects import BookingPage


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BookingItemResponse(ResponseModel):
    seat_id: str = Field(alias="seatId")
    ticket_type: str = Field(alias="ticketType")
    unit_price: Decimal = Field(alias="unitPrice")


class BookingResponse(ResponseModel):
    id: str
    booking_id: str = Field(alias="bookingId")
    customer_id: str = Field(alias="customerId")
    event_id: str = Field(alias="eventId")
    reservation_id: str = Field(alias="reservationId")
    payment_method: str = Field(alias="paymentMethod")
    items: list[BookingItemResponse]
    seats: list[str]
    total: Decimal
    total_amount: Decimal = Field(alias="totalAmount")
    currency: str
    status: BookingStatus
    payment_status: PaymentStatus = Field(alias="paymentStatus")
    payment_id: str | None = Field(default=None, alias="paymentId")
    failure_code: str | None = Field(default=None, alias="failureCode")
    failure_reason: str | None = Field(default=None, alias="failureReason")
    cancellation_reason: str | None = Field(default=None, alias="cancellationReason")
    resource_version: int = Field(alias="resourceVersion")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    confirmed_at: datetime | None = Field(default=None, alias="confirmedAt")
    cancelled_at: datetime | None = Field(default=None, alias="cancelledAt")

    @classmethod
    def from_entity(cls, booking: Booking) -> BookingResponse:
        return cls(
            id=booking.booking_id,
            bookingId=booking.booking_id,
            customerId=booking.customer_id,
            eventId=booking.event_id,
            reservationId=booking.reservation_id,
            paymentMethod=booking.payment_method,
            items=[
                BookingItemResponse(
                    seatId=item.seat_id,
                    ticketType=item.ticket_type,
                    unitPrice=item.unit_price,
                )
                for item in booking.items
            ],
            seats=[item.seat_id for item in booking.items],
            total=booking.total_amount,
            totalAmount=booking.total_amount,
            currency=booking.currency,
            status=booking.status,
            paymentStatus=booking.payment_status,
            paymentId=booking.payment_id,
            failureCode=booking.failure_code,
            failureReason=booking.failure_reason,
            cancellationReason=booking.cancellation_reason,
            resourceVersion=booking.resource_version,
            createdAt=booking.created_at,
            updatedAt=booking.updated_at,
            confirmedAt=booking.confirmed_at,
            cancelledAt=booking.cancelled_at,
        )


class BookingPageResponse(ResponseModel):
    items: list[BookingResponse]
    page: int
    page_size: int = Field(alias="pageSize")
    total: int
    total_pages: int = Field(alias="totalPages")

    @classmethod
    def from_page(cls, result: BookingPage) -> BookingPageResponse:
        return cls(
            items=[BookingResponse.from_entity(item) for item in result.items],
            page=result.page,
            pageSize=result.page_size,
            total=result.total,
            totalPages=result.total_pages,
        )
