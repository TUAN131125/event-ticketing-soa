"""Entity thuan nghiep vu cua Event Service."""
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.enums import EventStatus
from app.domain.value_objects import TicketType


@dataclass
class Event:
    id: str
    name: str
    location: str
    start_time: str
    status: EventStatus
    ticket_types: list[TicketType] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def create(cls, event_id: str, name: str, location: str, start_time: str,
               ticket_types: list[TicketType]) -> "Event":
        return cls(
            id=event_id, name=name, location=location, start_time=start_time,
            status=EventStatus.DRAFT, ticket_types=ticket_types,
        )

    def update_info(self, name: str | None = None, location: str | None = None,
                     start_time: str | None = None) -> None:
        if name is not None:
            self.name = name
        if location is not None:
            self.location = location
        if start_time is not None:
            self.start_time = start_time
