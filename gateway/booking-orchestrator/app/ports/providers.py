from __future__ import annotations

from typing import Any, Protocol

from app.domain.models import RequestContext


class CustomerPort(Protocol):
    async def resolve_identity(
        self, subject: str, ctx: RequestContext
    ) -> dict[str, Any]: ...


class EventPort(Protocol):
    async def list_events(
        self, params: dict[str, Any], ctx: RequestContext
    ) -> Any: ...

    async def get_event(
        self, event_id: str, ctx: RequestContext
    ) -> dict[str, Any]: ...

    async def check_sale_eligibility(
        self, event_id: str, ctx: RequestContext
    ) -> dict[str, Any]: ...

    async def admin_command(
        self,
        operation: str,
        event_id: str | None,
        payload: dict[str, Any],
        headers: dict[str, str],
        ctx: RequestContext,
    ) -> Any: ...


class SeatPort(Protocol):
    async def get_seat_map(
        self, event_id: str, ctx: RequestContext
    ) -> dict[str, Any]: ...

    async def check_availability(
        self,
        event_id: str,
        seat_references: list[dict[str, str]],
        ctx: RequestContext,
    ) -> dict[str, Any]: ...

    async def reserve(
        self,
        booking_id: str,
        event_id: str,
        seat_references: list[dict[str, str]],
        ttl_seconds: int,
        idempotency_key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]: ...

    async def confirm(
        self,
        reservation_id: str,
        expected_version: int,
        idempotency_key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]: ...

    async def release(
        self,
        reservation_id: str,
        reason_code: str,
        idempotency_key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]: ...


class BookingPort(Protocol):
    async def create(
        self, payload: dict[str, Any], key: str, ctx: RequestContext
    ) -> dict[str, Any]: ...

    async def get(
        self, booking_id: str, ctx: RequestContext
    ) -> dict[str, Any]: ...

    async def list_customer(
        self, customer_id: str, params: dict[str, Any], ctx: RequestContext
    ) -> Any: ...

    async def attach_reservation(
        self,
        booking_id: str,
        payload: dict[str, Any],
        key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]: ...

    async def confirm_reservation(
        self,
        booking_id: str,
        payload: dict[str, Any],
        key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]: ...

    async def start_payment(
        self,
        booking_id: str,
        payload: dict[str, Any],
        key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]: ...

    async def record_payment(
        self,
        booking_id: str,
        payload: dict[str, Any],
        key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]: ...

    async def attach_tickets(
        self,
        booking_id: str,
        payload: dict[str, Any],
        key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]: ...

    async def confirm(
        self,
        booking_id: str,
        payload: dict[str, Any],
        key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]: ...

    async def fail(
        self,
        booking_id: str,
        payload: dict[str, Any],
        key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]: ...

    async def cancel(
        self,
        booking_id: str,
        payload: dict[str, Any],
        key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]: ...

    async def record_compensation(
        self,
        booking_id: str,
        payload: dict[str, Any],
        key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]: ...


class PaymentPort(Protocol):
    async def create(
        self, payload: dict[str, Any], key: str, ctx: RequestContext
    ) -> dict[str, Any]: ...

    async def authorize(
        self,
        payment_id: str,
        payload: dict[str, Any],
        key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]: ...

    async def capture(
        self,
        payment_id: str,
        payload: dict[str, Any],
        key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]: ...

    async def get(
        self, payment_id: str, ctx: RequestContext
    ) -> dict[str, Any]: ...

    async def cancel(
        self,
        payment_id: str,
        payload: dict[str, Any],
        key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]: ...

    async def refund(
        self,
        payment_id: str,
        payload: dict[str, Any],
        key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]: ...

    async def reconcile(
        self,
        payment_id: str,
        payload: dict[str, Any],
        key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]: ...


class TicketPort(Protocol):
    async def issue(
        self, payload: dict[str, Any], key: str, ctx: RequestContext
    ) -> dict[str, Any]: ...

    async def get(
        self, ticket_id: str, ctx: RequestContext
    ) -> dict[str, Any]: ...

    async def list_booking(self, booking_id: str, ctx: RequestContext) -> Any: ...

    async def validate(
        self,
        payload: dict[str, Any],
        key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]: ...

    async def check_in(
        self,
        ticket_id: str,
        payload: dict[str, Any],
        headers: dict[str, str],
        ctx: RequestContext,
    ) -> dict[str, Any]: ...

    async def cancel(
        self,
        ticket_id: str,
        payload: dict[str, Any],
        key: str,
        ctx: RequestContext,
    ) -> dict[str, Any]: ...


class RealtimePort(Protocol):
    async def issue_ticket(
        self, payload: dict[str, Any], ctx: RequestContext
    ) -> dict[str, Any]: ...


class SubscriberPort(Protocol):
    async def publish(
        self,
        topic: str,
        payload: dict[str, Any],
        message_id: str,
        ctx: RequestContext | None = None,
    ) -> None: ...
