from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class BookingStatus(str, Enum):
    PENDING = "PENDING"
    SEAT_RESERVED = "SEAT_RESERVED"
    PAYMENT_PROCESSING = "PAYMENT_PROCESSING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    COMPENSATION_PENDING = "COMPENSATION_PENDING"


class BookingPaymentStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"


class EventStatus(str, Enum):
    DRAFT = "DRAFT"
    ON_SALE = "ON_SALE"
    PAUSED = "PAUSED"
    CANCELLED = "CANCELLED"
    ENDED = "ENDED"


class TicketStatus(str, Enum):
    ISSUED = "ISSUED"
    CHECKED_IN = "CHECKED_IN"
    CANCELLED = "CANCELLED"


class SeatAvailability(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"



class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class AuthRole(str, Enum):
    CUSTOMER = "CUSTOMER"
    ADMIN = "ADMIN"
    CHECKIN_STAFF = "CHECKIN_STAFF"
    SERVICE = "SERVICE"


class RegisterRequest(ClosedModel):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(ClosedModel):
    email: EmailStr = Field(max_length=320)
    password: str = Field(min_length=12, max_length=128)


class User(ClosedModel):
    userId: str
    email: EmailStr
    status: Literal["ACTIVE", "DISABLED"]
    roles: list[AuthRole]
    tokenVersion: int = Field(ge=1)
    createdAt: datetime


class TokenResponse(ClosedModel):
    accessToken: str = Field(min_length=1)
    tokenType: Literal["Bearer"]
    expiresIn: int = Field(ge=1)
    csrfToken: str = Field(min_length=32)
    user: User


class ErrorBody(ClosedModel):
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{1,63}$")
    message: str = Field(min_length=1, max_length=500)
    retryable: bool
    details: dict[str, Any] | None = None


class ErrorResponse(ClosedModel):
    correlationId: str = Field(min_length=1, max_length=128)
    traceId: str | None = Field(default=None, pattern=r"^[A-Fa-f0-9]{16,32}$")
    error: ErrorBody


class Money(ClosedModel):
    amountMinor: int = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class TicketTypeProjection(ClosedModel):
    ticketTypeId: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    price: Money


class PublicEvent(ClosedModel):
    eventId: str
    name: str
    venue: str
    startsAt: datetime
    saleStartsAt: datetime | None = None
    saleEndsAt: datetime | None = None
    status: EventStatus
    ticketTypes: list[TicketTypeProjection]
    resourceVersion: int = Field(ge=1)


class PlaceBookingRequest(ClosedModel):
    customerId: str | None = Field(
        default=None,
        deprecated=True,
        description="Compatibility only. ESB resolves ownership from the authenticated identity.",
    )
    eventId: str = Field(min_length=1, max_length=128)
    seatIds: list[str] = Field(min_length=1, max_length=10)
    paymentMethodToken: str = Field(min_length=8, max_length=256)

    @field_validator("seatIds")
    @classmethod
    def unique_seats(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("seatIds must not contain blank values")
        if len(normalized) != len(set(normalized)):
            raise ValueError("seatIds must be unique")
        return normalized


class BookingResult(ClosedModel):
    bookingId: str
    eventId: str
    seatIds: list[str]
    status: BookingStatus
    total: Money
    reservationId: str | None = None
    paymentId: str | None = None
    ticketIds: list[str]
    correlationId: str
    paymentStatus: BookingPaymentStatus | None = None
    workflowId: str | None = None
    resourceVersion: int = Field(ge=1)
    createdAt: datetime | None = None
    updatedAt: datetime | None = None


class BookingListProjection(ClosedModel):
    items: list[BookingResult]
    page: int = Field(ge=1)
    pageSize: int = Field(ge=1, le=100)
    totalItems: int = Field(ge=0)


class CancelBookingRequest(ClosedModel):
    reason: str = Field(default="USER_REQUEST", min_length=1, max_length=2000)


class SeatProjection(ClosedModel):
    seatId: str
    seatCode: str
    section: str | None = None
    row: str | None = None
    ticketTypeId: str
    ticketTypeName: str
    status: SeatAvailability
    price: Money


class SeatMapProjection(ClosedModel):
    eventId: str
    generatedAt: datetime
    seats: list[SeatProjection]


class TicketProjection(ClosedModel):
    ticketId: str
    bookingId: str
    eventId: str
    eventName: str
    venue: str
    startsAt: str
    seatId: str
    seatCode: str
    ticketTypeName: str
    status: TicketStatus
    qrToken: str | None = Field(
        default=None,
        description="Owner-only secret. Never log or persist in browser storage.",
    )
    correlationId: str
    resourceVersion: int = Field(ge=1)


class TicketListProjection(ClosedModel):
    items: list[TicketProjection]
    page: int = Field(ge=1)
    pageSize: int = Field(ge=1, le=100)
    totalItems: int = Field(ge=0)


class MoneyRequest(Money):
    pass


class AdminTicketTypeInput(ClosedModel):
    ticketTypeId: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    price: MoneyRequest


class EventAdminRequest(ClosedModel):
    """Transport validation only. Event Service remains domain authority."""

    name: str = Field(min_length=2, max_length=300)
    venue: str = Field(min_length=1, max_length=500)
    startsAt: str
    saleStartsAt: str
    saleEndsAt: str
    ticketTypes: list[AdminTicketTypeInput] = Field(min_length=1, max_length=200)

    @field_validator("startsAt", "saleStartsAt", "saleEndsAt")
    @classmethod
    def utc_datetime(cls, value: str) -> str:
        normalized = value.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError as exc:
            raise ValueError("must be an ISO-8601 date-time") from exc
        if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
            raise ValueError("must use UTC (Z or +00:00)")
        return value


class CheckInValidateRequest(ClosedModel):
    qrToken: str = Field(min_length=16, max_length=4096)


class CheckInRequest(ClosedModel):
    qrToken: str = Field(min_length=16, max_length=4096)


class TicketValidationResult(ClosedModel):
    valid: bool
    ticket: TicketProjection | None = None
    code: str | None = None
    message: str | None = None
    correlationId: str


class CheckInResult(ClosedModel):
    ticket: TicketProjection
    correlationId: str


class WsTicketRequest(ClosedModel):
    bookingId: str = Field(min_length=1, max_length=128)


class WsTicketResponse(ClosedModel):
    ticket: str = Field(min_length=16, max_length=4096)
    bookingId: str = Field(min_length=1, max_length=128)
    expiresAt: datetime


class TraceStep(ClosedModel):
    service: str
    operation: str
    status: str
    durationMs: int = Field(ge=0)
    errorCode: str | None = None


class DependencyHealth(ClosedModel):
    name: str
    critical: bool
    status: Literal["UP", "DOWN"]
    latencyMs: int | None = Field(default=None, ge=0)
    errorCode: Literal["TIMEOUT", "UNREACHABLE", "NOT_READY"] | None = None


class AggregateHealth(ClosedModel):
    status: Literal["UP", "DEGRADED", "DOWN"]
    checkedAt: datetime
    dependencies: list[DependencyHealth]


class HealthStatus(ClosedModel):
    status: Literal["UP", "READY", "NOT_READY"]
    service: str | None = None
    version: str | None = None


class CustomerProfileInput(ClosedModel):
    fullName: str = Field(min_length=2, max_length=150)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)


class CustomerProfileProjection(ClosedModel):
    customerId: str
    fullName: str
    email: EmailStr
    phone: str | None = None
    status: Literal["ACTIVE", "INACTIVE", "ANONYMIZED"]
    resourceVersion: int = Field(ge=1)
    createdAt: datetime
    updatedAt: datetime


class ConsentUpdateRequest(ClosedModel):
    channel: Literal["EMAIL", "SMS"]
    granted: bool


class ConsentUpdateResult(ClosedModel):
    customerId: str
    channel: Literal["EMAIL", "SMS"]
    granted: bool
    resourceVersion: int = Field(ge=1)


class AdminSeatDefinition(ClosedModel):
    seatId: str = Field(min_length=1, max_length=128)
    section: str = Field(min_length=1, max_length=100)
    rowLabel: str = Field(min_length=1, max_length=100)
    seatNumber: str = Field(min_length=1, max_length=100)
    ticketTypeId: str = Field(min_length=1, max_length=64)
    status: Literal["AVAILABLE", "BLOCKED"] = "AVAILABLE"


class ConfigureSeatInventoryRequest(ClosedModel):
    inventoryVersion: int = Field(ge=1)
    seats: list[AdminSeatDefinition] = Field(min_length=1, max_length=20000)


class ConfigureSeatInventoryResult(ClosedModel):
    eventId: str
    inventoryVersion: int = Field(ge=1)
    configuredSeatCount: int = Field(ge=0)
    status: Literal["CONFIGURED", "REPLAYED"]


class AdminSeatInventoryProjection(ClosedModel):
    eventId: str
    generatedAt: datetime
    seats: list[SeatProjection]
