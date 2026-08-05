"""Canonical Event aggregate."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.enums import EventStatus
from app.domain.value_objects import TicketType


@dataclass
class Event:
    id: str
    name: str
    venue: str
    starts_at: datetime
    sale_starts_at: datetime
    sale_ends_at: datetime
    status: EventStatus
    ticket_types: list[TicketType] = field(default_factory=list)
    resource_version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(
        cls,
        event_id: str,
        name: str,
        venue: str,
        starts_at: datetime,
        sale_starts_at: datetime,
        sale_ends_at: datetime,
        ticket_types: list[TicketType],
    ) -> Event:
        return cls(
            id=event_id,
            name=name,
            venue=venue,
            starts_at=starts_at,
            sale_starts_at=sale_starts_at,
            sale_ends_at=sale_ends_at,
            status=EventStatus.DRAFT,
            ticket_types=ticket_types,
        )

    def replace(
        self,
        *,
        name: str,
        venue: str,
        starts_at: datetime,
        sale_starts_at: datetime,
        sale_ends_at: datetime,
        ticket_types: list[TicketType],
    ) -> None:
        self.name = name
        self.venue = venue
        self.starts_at = starts_at
        self.sale_starts_at = sale_starts_at
        self.sale_ends_at = sale_ends_at
        self.ticket_types = ticket_types
        self.touch()

    def touch(self) -> None:
        self.resource_version += 1
        self.updated_at = datetime.now(UTC)
