from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ErrorDetail(StrictModel):
    code: str
    message: str
    retryable: bool
    details: dict[str, Any] | None = None


class ErrorResponse(StrictModel):
    correlationId: str
    traceId: str | None = None
    error: ErrorDetail


class MoneyModel(StrictModel):
    amountMinor: int = Field(ge=0, le=9223372036854775807)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class PlaceBookingRequest(StrictModel):
    customerId: str
    eventId: str
    seatIds: list[str] = Field(min_length=1, max_length=10)
    paymentMethodToken: str = Field(min_length=6, max_length=200)

    @field_validator("seatIds")
    @classmethod
    def unique_seats(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("seatIds must be unique")
        return value


class BookingResult(StrictModel):
    bookingId: str
    status: str
    total: MoneyModel
    reservationId: str | None = None
    paymentId: str | None = None
    ticketIds: list[str] = Field(default_factory=list)
    correlationId: str


class PublicEvent(BaseModel):
    eventId: str
    name: str
    venue: str
    startsAt: datetime
    status: str
    ticketTypes: list[dict[str, Any]]


class TraceStep(BaseModel):
    service: str
    operation: str
    status: str
    durationMs: int
    errorCode: str | None = None


class DependencyHealthStatus(BaseModel):
    name: str
    critical: bool
    status: str
    latencyMs: int | None = None
    errorCode: str | None = None


class AggregateHealthStatus(BaseModel):
    status: str
    checkedAt: datetime
    dependencies: list[DependencyHealthStatus]


class WsTicketRequest(StrictModel):
    bookingId: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$")


class WsTicketResponse(StrictModel):
    ticket: str = Field(min_length=16, max_length=4096)
    bookingId: str
    expiresAt: datetime
