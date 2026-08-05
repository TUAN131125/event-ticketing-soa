"""Canonical Booking response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import Booking


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MoneyResponse(ResponseModel):
    amount_minor: int = Field(alias="amountMinor", ge=0)
    currency: str


class BookingItemResponse(ResponseModel):
    seat_id: str = Field(alias="seatId")
    ticket_type_code: str = Field(alias="ticketTypeCode")
    unit_price: MoneyResponse = Field(alias="unitPrice")


class BookingResponse(ResponseModel):
    booking_id: str = Field(alias="bookingId")
    customer_id: str = Field(alias="customerId")
    event_id: str = Field(alias="eventId")
    status: str
    items: list[BookingItemResponse]
    total: MoneyResponse
    reservation_id: str | None = Field(default=None, alias="reservationId")
    payment_id: str | None = Field(default=None, alias="paymentId")
    ticket_ids: list[str] = Field(default_factory=list, alias="ticketIds")
    resource_version: int = Field(alias="resourceVersion", ge=1)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    @classmethod
    def from_entity(cls, booking: Booking) -> BookingResponse:
        return cls(
            bookingId=booking.booking_id,
            customerId=booking.customer_id,
            eventId=booking.event_id,
            status=booking.status.value,
            items=[
                BookingItemResponse(
                    seatId=item.seat_id,
                    ticketTypeCode=item.ticket_type_code,
                    unitPrice=MoneyResponse(
                        amountMinor=int(item.unit_price), currency=booking.currency
                    ),
                )
                for item in booking.items
            ],
            total=MoneyResponse(
                amountMinor=int(booking.total_amount), currency=booking.currency
            ),
            reservationId=booking.reservation_id,
            paymentId=booking.payment_id,
            ticketIds=list(booking.ticket_ids),
            resourceVersion=booking.resource_version,
            createdAt=booking.created_at,
            updatedAt=booking.updated_at,
        )


class BookingAccessDecisionResponse(ResponseModel):
    allowed: bool
    reason_code: str = Field(alias="reasonCode")
    cache_ttl_seconds: int = Field(alias="cacheTtlSeconds", ge=0, le=5)
