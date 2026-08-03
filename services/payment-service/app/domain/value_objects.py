"""Immutable values used by the payment aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from app.domain.enums import RefundKind

if TYPE_CHECKING:
    from app.domain.entities import Payment


@dataclass(frozen=True, slots=True)
class Refund:
    refund_id: str
    payment_id: str
    amount: Decimal
    currency: str
    reason: str
    kind: RefundKind
    provider_reference: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RequestContext:
    correlation_id: str
    caller_service: str
    actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class PaymentPage:
    items: tuple[Payment, ...]
    page: int
    page_size: int
    total: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total + self.page_size - 1) // self.page_size)
