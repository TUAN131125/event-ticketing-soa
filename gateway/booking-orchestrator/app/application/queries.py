from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.domain.errors import AccessDenied
from app.domain.models import RequestContext
from app.ports.providers import BookingPort, EventPort
from app.ports.repositories import TraceRepository


class QueryService:
    def __init__(self, events: EventPort, bookings: BookingPort, traces: TraceRepository) -> None:
        self.events, self.bookings, self.traces = events, bookings, traces

    async def list_events(self, context: RequestContext) -> Sequence[Mapping[str, Any]]:
        return await self.events.list_events(context)

    async def get_event(self, event_id: str, context: RequestContext) -> Mapping[str, Any]:
        return await self.events.get_event(event_id, context)

    async def get_booking(self, booking_id: str, context: RequestContext) -> Mapping[str, Any]:
        decision = await self.bookings.decide_access(booking_id, context)
        if not decision.get("allowed"):
            raise AccessDenied()
        booking = await self.bookings.get_booking(booking_id, context)
        return {
            "bookingId": booking["bookingId"],
            "status": booking["status"],
            "total": booking["total"],
            "reservationId": booking.get("reservationId"),
            "paymentId": booking.get("paymentId"),
            "ticketIds": booking.get("ticketIds", []),
            "correlationId": context.correlation_id,
        }

    async def trace(self, correlation_id: str, context: RequestContext) -> Sequence[Mapping[str, Any]]:
        if "ADMIN" not in context.principal.roles:
            raise AccessDenied()
        return await self.traces.list(correlation_id)
