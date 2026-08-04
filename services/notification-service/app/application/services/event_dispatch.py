"""Bang dieu phoi theo eventType (Muc 2 dac ta SVC-08): moi eventType xac
dinh template_code va cach trich xuat (destination, field de dien
template) tu truong `data` cua EventEnvelope.

Tach rieng file nay de them 1 eventType moi (vi du "payment.refunded" o
giai doan sau) chi can them 1 dong o day, khong phai sua use case."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.application.services.template_defaults import EVENT_TYPE_TEMPLATE_CODE
from app.domain.exceptions import EventSchemaInvalidError


@dataclass(frozen=True)
class EventDispatchResult:
    template_code: str
    destination: str
    template_fields: dict[str, str]


def _booking_confirmed(data: dict[str, Any]) -> EventDispatchResult:
    if "bookingId" not in data or "email" not in data:
        raise EventSchemaInvalidError("data.bookingId va data.email la bat buoc cho booking.confirmed")
    return EventDispatchResult(
        template_code="booking_confirmed",
        destination=data["email"],
        template_fields={
            "customer_name": data.get("customerName", data["email"]),
            "booking_id": data["bookingId"],
            "ticket_ids": ", ".join(data.get("ticketIds", [])),
        },
    )


def _booking_failed(data: dict[str, Any]) -> EventDispatchResult:
    if "bookingId" not in data or "email" not in data:
        raise EventSchemaInvalidError("data.bookingId va data.email la bat buoc cho booking.failed")
    return EventDispatchResult(
        template_code="booking_failed",
        destination=data["email"],
        template_fields={
            "booking_id": data["bookingId"],
            "reason": data.get("reason", ""),
        },
    )


def _event_changed(data: dict[str, Any]) -> EventDispatchResult:
    if "eventId" not in data or "email" not in data:
        raise EventSchemaInvalidError("data.eventId va data.email la bat buoc cho event.changed")
    return EventDispatchResult(
        template_code="event_changed",
        destination=data["email"],
        template_fields={
            "event_id": data["eventId"],
            "change_summary": data.get("changeSummary", ""),
        },
    )


def _ticket_issued(data: dict[str, Any]) -> EventDispatchResult:
    if "ticketId" not in data or "eventId" not in data or "email" not in data:
        raise EventSchemaInvalidError(
            "data.ticketId, data.eventId va data.email la bat buoc cho ticket.issued"
        )
    return EventDispatchResult(
        template_code="ticket_issued",
        destination=data["email"],
        template_fields={"ticket_id": data["ticketId"], "event_id": data["eventId"]},
    )


_DISPATCH_TABLE: dict[str, Callable[[dict[str, Any]], EventDispatchResult]] = {
    "booking.confirmed": _booking_confirmed,
    "booking.failed": _booking_failed,
    "event.changed": _event_changed,
    "ticket.issued": _ticket_issued,
}


def dispatch(event_type: str, data: dict[str, Any]) -> EventDispatchResult:
    handler = _DISPATCH_TABLE.get(event_type)
    if handler is None:
        raise EventSchemaInvalidError(f"eventType khong duoc ho tro: {event_type}")
    result = handler(data)
    assert result.template_code == EVENT_TYPE_TEMPLATE_CODE[event_type]
    return result
