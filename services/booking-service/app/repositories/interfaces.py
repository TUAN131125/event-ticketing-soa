"""Read-side repository boundary for alternate adapters and tests."""

from typing import Protocol

from app.domain.entities import Booking
from app.domain.enums import BookingStatus
from app.domain.value_objects import BookingPage


class BookingReadRepository(Protocol):
    def get(self, booking_id: str) -> Booking | None: ...

    def list(
        self,
        *,
        page: int,
        page_size: int,
        customer_id: str | None = None,
        event_id: str | None = None,
        status: BookingStatus | None = None,
        search: str | None = None,
    ) -> BookingPage: ...
