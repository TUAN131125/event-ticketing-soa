"""Read-side repository boundary for alternate adapters and tests."""

from typing import Protocol

from app.domain.entities import Ticket
from app.domain.enums import TicketStatus
from app.domain.value_objects import TicketPage


class TicketReadRepository(Protocol):
    def get(self, ticket_id: str) -> Ticket | None: ...

    def list(
        self,
        *,
        page: int,
        page_size: int,
        booking_id: str | None = None,
        customer_id: str | None = None,
        event_id: str | None = None,
        status: TicketStatus | None = None,
        search: str | None = None,
    ) -> TicketPage: ...
