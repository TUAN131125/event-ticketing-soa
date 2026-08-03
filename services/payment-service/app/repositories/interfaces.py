"""Read-side repository boundary for alternate adapters and tests."""

from typing import Protocol

from app.domain.entities import Payment
from app.domain.enums import PaymentStatus
from app.domain.value_objects import PaymentPage


class PaymentReadRepository(Protocol):
    def get(self, payment_id: str) -> Payment | None: ...

    def list(
        self,
        *,
        page: int,
        page_size: int,
        booking_id: str | None = None,
        customer_id: str | None = None,
        provider: str | None = None,
        status: PaymentStatus | None = None,
        search: str | None = None,
    ) -> PaymentPage: ...
