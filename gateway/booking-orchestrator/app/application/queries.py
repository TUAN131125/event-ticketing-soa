from __future__ import annotations

import asyncio
from typing import Any

from app.application.projections import (
    booking_page_projection,
    booking_projection,
    event_projection,
    generated_at,
    seat_projection,
    seat_rows,
    ticket_projection,
)
from app.domain.errors import EsbError, Forbidden
from app.domain.models import RequestContext


class QueryService:
    """Frontend-facing query façade over authoritative provider services.

    Provider payloads never escape directly to the browser.  This class performs
    protocol-safe projection only; provider services remain authoritative for
    event, seat, booking and ticket state.
    """

    def __init__(self, event, seat, booking, ticket, customer) -> None:
        self.event = event
        self.seat = seat
        self.booking = booking
        self.ticket = ticket
        self.customer = customer

    async def customer_id(self, ctx: RequestContext) -> str:
        if ctx.principal.customer_id:
            return ctx.principal.customer_id
        customer = await self.customer.resolve_identity(ctx.principal.subject, ctx)
        return str(customer.get("customerId") or customer.get("id"))

    async def event_list(self, params: dict[str, Any], ctx: RequestContext) -> list[dict[str, Any]]:
        raw = await self.event.list_events(params, ctx)
        rows = raw.get("items", raw.get("events", [])) if isinstance(raw, dict) else raw
        return [event_projection(item) for item in list(rows or []) if isinstance(item, dict)]

    async def event_get(self, event_id: str, ctx: RequestContext) -> dict[str, Any]:
        return event_projection(await self.event.get_event(event_id, ctx))

    async def seat_map(self, event_id: str, ctx: RequestContext) -> dict[str, Any]:
        raw_event, inventory = await asyncio.gather(
            self.event.get_event(event_id, ctx),
            self.seat.get_seat_map(event_id, ctx),
        )
        event_view = event_projection(raw_event)
        ticket_types = {
            item["ticketTypeId"]: item for item in event_view["ticketTypes"]
        }
        rows = seat_rows(inventory)

        def project(row: dict[str, Any]) -> dict[str, Any]:
            # GetSeatMap is the authoritative bulk query for the UI. Calling
            # CheckAvailability once per seat would create an unbounded N+1 fan-out.
            provider_status = str(row.get("status") or "").upper()
            if provider_status not in {"AVAILABLE", "HELD", "SOLD", "BLOCKED"}:
                raise EsbError(
                    "INVALID_PROVIDER_RESPONSE",
                    "Seat Inventory GetSeatMap omitted a valid seat status",
                    502,
                    True,
                )
            return seat_projection(
                row,
                status="AVAILABLE" if provider_status == "AVAILABLE" else "UNAVAILABLE",
                event_ticket_types=ticket_types,
            )

        seats = [project(row) for row in rows]
        return {
            "eventId": event_view["eventId"],
            "generatedAt": generated_at(),
            "seats": seats,
        }

    async def booking_get(
        self,
        booking_id: str,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        booking = await self._owned_booking(booking_id, ctx)
        return booking_projection(booking, ctx)

    async def _owned_booking(
        self,
        booking_id: str,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        booking = await self.booking.get(booking_id, ctx)
        customer_id = await self.customer_id(ctx)
        if str(booking.get("customerId")) != str(customer_id):
            raise Forbidden("Booking does not belong to authenticated customer")
        return booking

    async def booking_list(
        self,
        params: dict[str, Any],
        ctx: RequestContext,
    ) -> dict[str, Any]:
        customer_id = await self.customer_id(ctx)
        page = max(1, int(params.get("page") or 1))
        page_size = max(1, min(100, int(params.get("pageSize") or 20)))
        # listCustomerBookings accepts page and pageSize only. The broad admin list is the
        # only operation with a status filter, and it is not an owner-scoped surface, so a
        # status filter is not pushed down here. Filtering client-side would break paging,
        # so the parameter is deliberately not honoured rather than silently mis-paged.
        provider_params = {
            "page": page,
            "pageSize": page_size,
        }
        raw = await self.booking.list_customer(customer_id, provider_params, ctx)
        return booking_page_projection(raw, ctx, page=page, page_size=page_size)

    async def booking_tickets(
        self,
        booking_id: str,
        ctx: RequestContext,
    ) -> list[dict[str, Any]]:
        booking = await self._owned_booking(booking_id, ctx)
        raw = await self.ticket.list_booking(booking_id, ctx)
        rows = self._items(raw, "tickets")
        return [
            await self._project_ticket(item, booking, ctx, include_qr=False)
            for item in rows
            if isinstance(item, dict)
        ]

    async def ticket_get(
        self,
        ticket_id: str,
        ctx: RequestContext,
    ) -> dict[str, Any]:
        ticket = await self.ticket.get(ticket_id, ctx)
        customer_id = await self.customer_id(ctx)
        if str(ticket.get("customerId")) != str(customer_id):
            raise Forbidden("Ticket does not belong to authenticated customer")
        booking = await self.booking.get(str(ticket.get("bookingId")), ctx)
        return await self._project_ticket(ticket, booking, ctx, include_qr=True)

    async def ticket_list(
        self,
        ctx: RequestContext,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        page = max(1, page)
        page_size = max(1, min(100, page_size))
        customer_id = await self.customer_id(ctx)
        bookings_raw = await self.booking.list_customer(
            customer_id,
            {"page": 1, "pageSize": 100},
            ctx,
        )
        bookings = [item for item in self._items(bookings_raw, "bookings") if isinstance(item, dict)]

        async def list_for_booking(booking: dict[str, Any]) -> tuple[dict[str, Any], list[Any]]:
            booking_id = str(booking.get("bookingId") or booking.get("id") or "")
            raw = await self.ticket.list_booking(booking_id, ctx)
            return booking, self._items(raw, "tickets")

        grouped = await asyncio.gather(*(list_for_booking(item) for item in bookings)) if bookings else []
        projected: list[dict[str, Any]] = []
        for booking, tickets in grouped:
            for item in tickets:
                if isinstance(item, dict):
                    projected.append(
                        await self._project_ticket(item, booking, ctx, include_qr=False)
                    )
        projected.sort(key=lambda item: item["ticketId"])
        start = (page - 1) * page_size
        return {
            "items": projected[start : start + page_size],
            "page": page,
            "pageSize": page_size,
            "totalItems": len(projected),
        }

    async def staff_ticket_projection(
        self,
        ticket: dict[str, Any],
        ctx: RequestContext,
        *,
        include_qr: bool,
    ) -> dict[str, Any]:
        booking = await self.booking.get(str(ticket.get("bookingId")), ctx)
        return await self._project_ticket(ticket, booking, ctx, include_qr=include_qr)

    async def _project_ticket(
        self,
        ticket: dict[str, Any],
        booking: dict[str, Any] | None,
        ctx: RequestContext,
        *,
        include_qr: bool,
    ) -> dict[str, Any]:
        event = await self.event.get_event(str(ticket.get("eventId")), ctx)
        return ticket_projection(
            ticket,
            event=event,
            booking=booking,
            ctx=ctx,
            include_qr=include_qr,
        )

    @staticmethod
    def _items(value: Any, fallback_key: str) -> list[Any]:
        if isinstance(value, dict):
            rows = value.get("items", value.get(fallback_key, []))
        else:
            rows = value
        return list(rows or [])
