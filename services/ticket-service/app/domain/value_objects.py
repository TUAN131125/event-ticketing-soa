"""Immutable values used by the ticket aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.entities import Ticket


@dataclass(frozen=True, slots=True)
class TicketDefinition:
    seat_id: str
    seat_label: str
    ticket_type: str


@dataclass(frozen=True, slots=True)
class RequestContext:
    correlation_id: str
    caller_service: str
    actor_id: str | None = None
    actor_roles: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class TicketPage:
    items: tuple[Ticket, ...]
    page: int
    page_size: int
    total: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total + self.page_size - 1) // self.page_size)
