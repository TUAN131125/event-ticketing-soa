from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class WorkflowPhase(str, Enum):
    STARTED = "STARTED"
    PENDING = "PENDING"
    SEAT_RESERVED = "SEAT_RESERVED"
    PAYMENT_PROCESSING = "PAYMENT_PROCESSING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    COMPENSATION_PENDING = "COMPENSATION_PENDING"


class PaymentOutcome(str, Enum):
    NOT_DISPATCHED = "NOT_DISPATCHED"
    CREATED = "CREATED"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    DECLINED = "DECLINED"
    CANCELLED = "CANCELLED"
    UNKNOWN = "UNKNOWN"
    REFUNDED = "REFUNDED"


@dataclass(frozen=True)
class Principal:
    subject: str
    roles: tuple[str, ...]


@dataclass(frozen=True)
class RequestContext:
    correlation_id: str
    trace_id: str | None
    deadline_monotonic: float
    principal: Principal
    workflow_id: str | None = None


@dataclass(frozen=True)
class Money:
    amount_minor: int
    currency: str

    def as_wire(self) -> dict[str, Any]:
        return {"amountMinor": self.amount_minor, "currency": self.currency}


@dataclass(frozen=True)
class PlaceBookingCommand:
    browser_customer_id: str
    event_id: str
    seat_ids: tuple[str, ...]
    payment_method_token: str
    idempotency_key: str


@dataclass(frozen=True)
class OperationResult:
    status_code: int
    body: Mapping[str, Any]


@dataclass
class WorkflowEvidence:
    workflow_id: str
    operation: str
    subject: str
    request_hash: str
    correlation_id: str
    phase: WorkflowPhase = WorkflowPhase.STARTED
    booking_id: str | None = None
    customer_id: str | None = None
    reservation_id: str | None = None
    reservation_version: int | None = None
    payment_id: str | None = None
    payment_status: PaymentOutcome | None = None
    ticket_ids: list[str] = field(default_factory=list)
    total: Money | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    version: int = 1


@dataclass(frozen=True)
class IdempotencyDecision:
    kind: str
    workflow_id: str
    recorded_result: OperationResult | None = None


@dataclass(frozen=True)
class OutboxItem:
    message_id: str
    destination: str
    message_type: str
    payload: Mapping[str, Any]
    correlation_id: str


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
