"""Immutable values used by the booking aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.entities import Booking


@dataclass(frozen=True, slots=True)
class BookingItem:
    seat_id: str
    ticket_type_code: str
    unit_price: Decimal


@dataclass(frozen=True, slots=True)
class RequestContext:
    correlation_id: str
    caller_service: str
    actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class BookingPage:
    items: tuple[Booking, ...]
    page: int
    page_size: int
    total: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total + self.page_size - 1) // self.page_size)
