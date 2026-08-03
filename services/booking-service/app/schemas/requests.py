"""Closed request contracts for booking commands."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import PaymentStatus


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BookingItemRequest(ClosedModel):
    seat_id: str = Field(alias="seatId", min_length=1, max_length=128)
    ticket_type: str = Field(alias="ticketType", min_length=1, max_length=128)
    unit_price: Decimal = Field(
        alias="unitPrice", ge=0, max_digits=18, decimal_places=2
    )


class CreateBookingRequest(ClosedModel):
    customer_id: str = Field(alias="customerId", min_length=1, max_length=128)
    event_id: str = Field(alias="eventId", min_length=1, max_length=128)
    reservation_id: str = Field(alias="reservationId", min_length=1, max_length=128)
    payment_method: str = Field(alias="paymentMethod", min_length=1, max_length=40)
    items: list[BookingItemRequest] = Field(min_length=1, max_length=50)
    total_amount: Decimal = Field(
        alias="totalAmount", ge=0, max_digits=18, decimal_places=2
    )
    currency: str = Field(min_length=3, max_length=3)

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        return value.upper()


class ConfirmBookingRequest(ClosedModel):
    payment_id: str = Field(alias="paymentId", min_length=1, max_length=128)
    expected_version: int = Field(alias="expectedVersion", ge=1)


class FailBookingRequest(ClosedModel):
    failure_code: str = Field(alias="failureCode", min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=2_000)
    expected_version: int = Field(alias="expectedVersion", ge=1)


class CancelBookingRequest(ClosedModel):
    reason: str = Field(min_length=1, max_length=2_000)
    expected_version: int = Field(alias="expectedVersion", ge=1)
    payment_status: PaymentStatus | None = Field(default=None, alias="paymentStatus")
