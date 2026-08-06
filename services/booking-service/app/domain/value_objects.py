"""Immutable values used by Booking Service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from app.domain.enums import PaymentStatus

if TYPE_CHECKING:
    from app.domain.entities import Booking


@dataclass(frozen=True, slots=True)
class BookingItem:
    seat_id: str
    ticket_type: str
    unit_price: Decimal


@dataclass(frozen=True, slots=True)
class NewBookingRequest:
    customer_id: str
    event_id: str
    reservation_id: str | None
    payment_method: str | None
    items: tuple[BookingItem, ...]
    total_amount: Decimal
    currency: str


@dataclass(frozen=True, slots=True)
class RequestContext:
    correlation_id: str
    caller_service: str
    actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class CompensationEvidence:
    reservation_released: bool = False
    payment_refunded: bool = False
    provider_reference: str | None = None
    verified_at: datetime | None = None
    details: dict[str, Any] | None = None
    resolved_payment_status: PaymentStatus | None = None


@dataclass(frozen=True, slots=True)
class BookingPage:
    items: tuple[Booking, ...]
    page: int
    page_size: int
    total: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total + self.page_size - 1) // self.page_size)


@dataclass(frozen=True, slots=True)
class ReconciliationCandidate:
    booking_id: str
    status: str
    missing_evidence: tuple[str, ...]
    recommended_action: str
    resource_version: int
    updated_at: datetime
    compensation_status: str
    compensation_action: str


@dataclass(frozen=True, slots=True)
class ReconciliationPage:
    items: tuple[ReconciliationCandidate, ...]
    page: int
    page_size: int
    total: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total + self.page_size - 1) // self.page_size)


@dataclass(frozen=True, slots=True)
class BookingHistoryEntry:
    operation: str
    previous_status: str | None
    new_status: str
    caller_service: str
    actor_id: str | None
    correlation_id: str
    idempotency_key: str
    resource_version: int
    details: dict[str, Any]
    occurred_at: datetime
