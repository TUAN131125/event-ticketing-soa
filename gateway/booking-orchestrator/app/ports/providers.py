from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from app.domain.models import Money, RequestContext


class CustomerPort(Protocol):
    async def resolve_mapping(self, identity_subject: str, context: RequestContext) -> Mapping[str, Any]: ...
    async def get_customer(self, customer_id: str, context: RequestContext) -> Mapping[str, Any]: ...


class EventPort(Protocol):
    async def list_events(self, context: RequestContext) -> Sequence[Mapping[str, Any]]: ...
    async def get_event(self, event_id: str, context: RequestContext) -> Mapping[str, Any]: ...
    async def get_sale_eligibility(self, event_id: str, context: RequestContext) -> Mapping[str, Any]: ...


class SeatPort(Protocol):
    async def check_availability(self, event_id: str, seat_ids: Sequence[str], context: RequestContext) -> Mapping[str, Any]: ...
    async def reserve_seats(self, payload: Mapping[str, Any], idempotency_key: str, context: RequestContext) -> Mapping[str, Any]: ...
    async def get_reservation(self, reservation_id: str, context: RequestContext) -> Mapping[str, Any]: ...
    async def confirm_seats(
        self,
        reservation_id: str,
        expected_version: int,
        idempotency_key: str,
        context: RequestContext,
    ) -> Mapping[str, Any]: ...
    async def release_seats(
        self,
        reservation_id: str,
        reason: str,
        idempotency_key: str,
        context: RequestContext,
    ) -> Mapping[str, Any]: ...


class BookingPort(Protocol):
    async def create_booking(self, payload: Mapping[str, Any], idempotency_key: str, context: RequestContext) -> Mapping[str, Any]: ...
    async def get_booking(self, booking_id: str, context: RequestContext) -> Mapping[str, Any]: ...
    async def decide_access(self, booking_id: str, context: RequestContext) -> Mapping[str, Any]: ...
    async def transition(
        self,
        operation: str,
        booking_id: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        context: RequestContext,
    ) -> Mapping[str, Any]: ...


class PaymentPort(Protocol):
    async def create_payment(
        self,
        booking_id: str,
        amount: Money,
        method_token: str,
        idempotency_key: str,
        context: RequestContext,
    ) -> Mapping[str, Any]: ...
    async def get_payment(self, payment_id: str, context: RequestContext) -> Mapping[str, Any]: ...
    async def command(
        self,
        operation: str,
        payment_id: str,
        payload: Mapping[str, Any],
        idempotency_key: str,
        context: RequestContext,
    ) -> Mapping[str, Any]: ...


class TicketPort(Protocol):
    async def issue_tickets(
        self, payload: Mapping[str, Any], idempotency_key: str, context: RequestContext
    ) -> Sequence[Mapping[str, Any]]: ...
    async def list_booking_tickets(self, booking_id: str, context: RequestContext) -> Sequence[Mapping[str, Any]]: ...
    async def cancel_ticket(self, ticket_id: str, idempotency_key: str, context: RequestContext) -> Mapping[str, Any]: ...


class NotificationPort(Protocol):
    async def publish(self, payload: Mapping[str, Any], message_id: str, context: RequestContext) -> None: ...


class RealtimePort(Protocol):
    async def publish(self, payload: Mapping[str, Any], message_id: str, context: RequestContext) -> None: ...
