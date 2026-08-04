"""Entity thuan nghiep vu cua Event Service - khop schema Event trong
OpenAPI (startsAt/saleStartsAt/saleEndsAt/venue/resourceVersion thay cho
location/startTime don gian truoc day)."""

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
    ) -> "Event":
        return cls(
            id=event_id,
            name=name,
            venue=venue,
            starts_at=starts_at,
            sale_starts_at=sale_starts_at,
            sale_ends_at=sale_ends_at,
            status=EventStatus.DRAFT,
            ticket_types=ticket_types,
            resource_version=1,
        )

    def replace_profile(
        self,
        name: str,
        venue: str,
        starts_at: datetime,
        sale_starts_at: datetime,
        sale_ends_at: datetime,
        ticket_types: list[TicketType],
    ) -> None:
        """PUT /events/{id} - thay the toan bo profile (EVT-02). Khong doi
        status/id/resourceVersion - resourceVersion tang o tang
        repository khi ghi thanh cong (xem PostgresEventRepository.update)."""
        self.name = name
        self.venue = venue
        self.starts_at = starts_at
        self.sale_starts_at = sale_starts_at
        self.sale_ends_at = sale_ends_at
        self.ticket_types = ticket_types

    def transition_to(self, target: EventStatus) -> None:
        self.status = target
