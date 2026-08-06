from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class WorkflowStatus(StrEnum):
    STARTED = "STARTED"
    SEAT_RESERVED = "SEAT_RESERVED"
    PAYMENT_PROCESSING = "PAYMENT_PROCESSING"
    PAYMENT_UNKNOWN = "PAYMENT_UNKNOWN"
    SEAT_CONFIRMED = "SEAT_CONFIRMED"
    TICKETS_ISSUED = "TICKETS_ISSUED"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    CANCELLATION_PENDING = "CANCELLATION_PENDING"
    CANCELLED = "CANCELLED"
    COMPENSATION_PENDING = "COMPENSATION_PENDING"


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    UNKNOWN = "UNKNOWN"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"


@dataclass(slots=True)
class Principal:
    subject: str
    roles: frozenset[str] = frozenset()
    customer_id: str | None = None

    def require_any(self, *roles: str) -> None:
        from app.domain.errors import Forbidden

        if not self.roles.intersection(roles):
            raise Forbidden(f"One of these roles is required: {', '.join(roles)}")


@dataclass(slots=True)
class RequestContext:
    correlation_id: str
    trace_id: str
    deadline_monotonic: float
    principal: Principal

    @property
    def traceparent(self) -> str:
        return f"00-{self.trace_id}-0000000000000001-01"


@dataclass(slots=True, frozen=True)
class BookingItem:
    seat_id: str
    ticket_type: str
    unit_price: int
    currency: str

    def seat_reference(self) -> dict[str, str]:
        return {
            "seatId": self.seat_id,
            "ticketTypeCode": self.ticket_type,
        }


@dataclass(slots=True)
class Workflow:
    workflow_id: str
    idempotency_key: str
    request_hash: str
    customer_id: str
    event_id: str
    seat_ids: list[str]
    status: WorkflowStatus = WorkflowStatus.STARTED
    booking_id: str | None = None
    booking_version: int | None = None
    reservation_id: str | None = None
    reservation_version: int | None = None
    payment_id: str | None = None
    payment_status: PaymentStatus = PaymentStatus.PENDING
    ticket_ids: list[str] = field(default_factory=list)
    amount_minor: int = 0
    currency: str = "VND"
    evidence: dict[str, Any] = field(default_factory=dict)
    response_status: int | None = None
    response_body: dict[str, Any] | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class OutboxMessage:
    message_id: str
    topic: str
    payload: dict[str, Any]
    attempts: int = 0
    state: str = "PENDING"
    next_attempt_at: float = 0.0
    last_error: str | None = None
