from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.errors import EsbError
from app.domain.models import RequestContext


def _compact(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _required_text(value: Any, field: str, provider: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise EsbError(
            "INVALID_PROVIDER_RESPONSE",
            f"{provider} did not return required field {field}",
            502,
            True,
        )
    return text


def _required_positive_int(value: Any, field: str, provider: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise EsbError(
            "INVALID_PROVIDER_RESPONSE",
            f"{provider} did not return valid {field}",
            502,
            True,
        ) from exc
    if parsed < 1:
        raise EsbError(
            "INVALID_PROVIDER_RESPONSE",
            f"{provider} returned invalid {field}",
            502,
            True,
        )
    return parsed


def _minor_amount(value: Any, field: str, provider: str) -> int:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise EsbError(
            "INVALID_PROVIDER_RESPONSE",
            f"{provider} returned invalid {field}",
            502,
            True,
        ) from exc
    if not decimal.is_finite() or decimal < 0 or decimal != decimal.to_integral_value():
        raise EsbError(
            "INVALID_PROVIDER_RESPONSE",
            f"{provider} returned non-integer minor-unit {field}",
            502,
            True,
        )
    return int(decimal)


def money_projection(value: Any, *, currency: Any = None, provider: str) -> dict[str, Any]:
    if isinstance(value, dict):
        amount = value.get("amountMinor")
        currency = value.get("currency", currency)
    else:
        amount = value
    return {
        "amountMinor": _minor_amount(amount, "amountMinor", provider),
        "currency": _required_text(currency, "currency", provider).upper(),
    }


def ticket_type_projection(value: dict[str, Any]) -> dict[str, Any]:
    code = _required_text(
        value.get("ticketTypeId") or value.get("code"),
        "ticketTypes[].code",
        "Event Service",
    )
    return {
        "ticketTypeId": code,
        "name": _required_text(value.get("name"), "ticketTypes[].name", "Event Service"),
        "price": money_projection(value.get("price"), provider="Event Service"),
    }


def event_projection(value: dict[str, Any]) -> dict[str, Any]:
    raw_types = value.get("ticketTypes") or []
    if not isinstance(raw_types, list):
        raise EsbError(
            "INVALID_PROVIDER_RESPONSE",
            "Event Service returned invalid ticketTypes",
            502,
            True,
        )
    result = {
        "eventId": _required_text(value.get("eventId") or value.get("id"), "eventId", "Event Service"),
        "name": _required_text(value.get("name"), "name", "Event Service"),
        "venue": _required_text(value.get("venue"), "venue", "Event Service"),
        "startsAt": _required_text(value.get("startsAt"), "startsAt", "Event Service"),
        "saleStartsAt": value.get("saleStartsAt"),
        "saleEndsAt": value.get("saleEndsAt"),
        "status": _required_text(value.get("status"), "status", "Event Service"),
        "ticketTypes": [ticket_type_projection(item) for item in raw_types if isinstance(item, dict)],
        "resourceVersion": _required_positive_int(
            value.get("resourceVersion"), "resourceVersion", "Event Service"
        ),
    }
    return _compact(result)


def event_request_to_provider(value: dict[str, Any]) -> dict[str, Any]:
    provider_types: list[dict[str, Any]] = []
    for item in value.get("ticketTypes") or []:
        if not isinstance(item, dict):
            raise EsbError("VALIDATION_ERROR", "ticketTypes must contain objects", 422)
        code = item.get("ticketTypeId")
        provider_types.append(
            {
                "code": _required_text(code, "ticketTypes[].ticketTypeId", "ESB request"),
                "name": _required_text(item.get("name"), "ticketTypes[].name", "ESB request"),
                "price": money_projection(item.get("price"), provider="ESB request"),
            }
        )

    return {
        "name": value["name"],
        "venue": value["venue"],
        "startsAt": value["startsAt"],
        "saleStartsAt": value["saleStartsAt"],
        "saleEndsAt": value["saleEndsAt"],
        "ticketTypes": provider_types,
    }


def booking_projection(value: dict[str, Any], ctx: RequestContext) -> dict[str, Any]:
    booking_id = _required_text(value.get("bookingId") or value.get("id"), "bookingId", "Booking Service")
    currency = value.get("currency")
    raw_total = value.get("total")
    if isinstance(raw_total, dict):
        total = money_projection(raw_total, provider="Booking Service")
    else:
        total = money_projection(
            value.get("totalAmount", raw_total),
            currency=currency,
            provider="Booking Service",
        )

    raw_items = value.get("items") or []
    seat_ids = value.get("seatIds") or value.get("seats")
    if not seat_ids and isinstance(raw_items, list):
        seat_ids = [item.get("seatId") for item in raw_items if isinstance(item, dict) and item.get("seatId")]

    return _compact(
        {
            "bookingId": booking_id,
            "eventId": _required_text(value.get("eventId"), "eventId", "Booking Service"),
            "seatIds": list(seat_ids or []),
            "status": _required_text(value.get("status"), "status", "Booking Service"),
            "total": total,
            "reservationId": value.get("reservationId"),
            "paymentId": value.get("paymentId"),
            "ticketIds": list(value.get("ticketIds") or []),
            "correlationId": value.get("correlationId") or ctx.correlation_id,
            "paymentStatus": value.get("paymentStatus"),
            "workflowId": value.get("workflowId"),
            "resourceVersion": _required_positive_int(
                value.get("resourceVersion"), "resourceVersion", "Booking Service"
            ),
            "createdAt": value.get("createdAt"),
            "updatedAt": value.get("updatedAt"),
        }
    )


def booking_page_projection(value: Any, ctx: RequestContext, *, page: int, page_size: int) -> dict[str, Any]:
    if isinstance(value, dict):
        rows = value.get("items") or value.get("bookings") or []
        actual_page = int(value.get("page") or page)
        actual_page_size = int(value.get("pageSize") or page_size)
        total = int(value.get("totalItems", value.get("total", len(rows))))
    else:
        rows = list(value or [])
        actual_page = page
        actual_page_size = page_size
        total = len(rows)
    return {
        "items": [booking_projection(item, ctx) for item in rows if isinstance(item, dict)],
        "page": actual_page,
        "pageSize": actual_page_size,
        "totalItems": total,
    }


def seat_rows(value: dict[str, Any]) -> list[dict[str, Any]]:
    rows: Any = value.get("seats") or value.get("seat") or []
    if isinstance(rows, dict):
        rows = rows.get("seat") or rows.get("items") or []
    if isinstance(rows, dict):
        rows = [rows]
    return [item for item in list(rows or []) if isinstance(item, dict)]


def seat_projection(
    value: dict[str, Any],
    *,
    status: str,
    event_ticket_types: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    seat_id = _required_text(value.get("seatId") or value.get("id"), "seatId", "Seat Inventory")
    code = _required_text(
        value.get("ticketTypeCode") or value.get("ticketType"),
        "ticketTypeCode",
        "Seat Inventory",
    )
    ticket_type = event_ticket_types.get(code)
    if ticket_type is None:
        raise EsbError(
            "INVALID_PROVIDER_RESPONSE",
            f"Seat Inventory referenced unknown ticket type {code}",
            502,
            True,
        )
    return _compact(
        {
            "seatId": seat_id,
            "seatCode": value.get("seatCode") or seat_id,
            "section": value.get("section"),
            "row": value.get("row") or value.get("rowLabel"),
            "ticketTypeId": code,
            "ticketTypeName": ticket_type["name"],
            "status": status,
            "price": ticket_type["price"],
        }
    )


def ticket_projection(
    value: dict[str, Any],
    *,
    event: dict[str, Any],
    booking: dict[str, Any] | None,
    ctx: RequestContext,
    include_qr: bool,
) -> dict[str, Any]:
    seat_id = _required_text(value.get("seatId"), "seatId", "Ticket Service")
    event_view = event_projection(event)

    ticket_type_code: str | None = None
    if isinstance(booking, dict):
        for item in booking.get("items") or []:
            if isinstance(item, dict) and str(item.get("seatId")) == seat_id:
                ticket_type_code = str(item.get("ticketTypeCode") or item.get("ticketType") or "") or None
                break
    ticket_types = {item["ticketTypeId"]: item for item in event_view["ticketTypes"]}
    ticket_type = ticket_types.get(ticket_type_code or "")

    result = {
        "ticketId": _required_text(value.get("ticketId") or value.get("id"), "ticketId", "Ticket Service"),
        "bookingId": _required_text(value.get("bookingId"), "bookingId", "Ticket Service"),
        "eventId": _required_text(value.get("eventId"), "eventId", "Ticket Service"),
        "eventName": event_view.get("name"),
        "venue": event_view.get("venue"),
        "startsAt": event_view.get("startsAt"),
        "seatId": seat_id,
        "seatCode": value.get("seatCode") or seat_id,
        "ticketTypeName": _required_text(
            ticket_type.get("name") if ticket_type else None,
            "ticketTypeName",
            "Booking/Event projection",
        ),
        "status": _required_text(value.get("status"), "status", "Ticket Service"),
        "qrToken": value.get("qrToken") if include_qr else None,
        "correlationId": ctx.correlation_id,
        "resourceVersion": _required_positive_int(
            value.get("resourceVersion"), "resourceVersion", "Ticket Service"
        ),
    }
    return _compact(result)


def generated_at() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
