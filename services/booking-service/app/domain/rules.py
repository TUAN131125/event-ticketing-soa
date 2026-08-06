"""Pure booking invariants and deterministic request hashing."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.enums import BookingStatus
from app.domain.exceptions import InvalidRequest, InvalidStateTransition
from app.domain.value_objects import BookingItem, NewBookingRequest

IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
CURRENCY = re.compile(r"^[A-Z]{3}$")

ALLOWED_TRANSITIONS: dict[BookingStatus, frozenset[BookingStatus]] = {
    BookingStatus.PENDING: frozenset(
        {
            BookingStatus.SEAT_RESERVED,
            BookingStatus.FAILED,
            BookingStatus.CANCELLED,
            BookingStatus.COMPENSATION_PENDING,
        }
    ),
    BookingStatus.SEAT_RESERVED: frozenset(
        {
            BookingStatus.PAYMENT_PROCESSING,
            BookingStatus.FAILED,
            BookingStatus.CANCELLED,
            BookingStatus.COMPENSATION_PENDING,
        }
    ),
    BookingStatus.PAYMENT_PROCESSING: frozenset(
        {
            BookingStatus.CONFIRMED,
            BookingStatus.FAILED,
            BookingStatus.COMPENSATION_PENDING,
        }
    ),
    BookingStatus.CONFIRMED: frozenset(
        {BookingStatus.CANCELLED, BookingStatus.COMPENSATION_PENDING}
    ),
    BookingStatus.COMPENSATION_PENDING: frozenset(
        {BookingStatus.FAILED, BookingStatus.CANCELLED}
    ),
    BookingStatus.FAILED: frozenset(),
    BookingStatus.CANCELLED: frozenset(),
}


def validate_identifier(
    value: str, field: str, *, max_length: int = 128
) -> str:
    normalized = value.strip()
    if not IDENTIFIER.fullmatch(normalized) or len(normalized) > max_length:
        raise InvalidRequest(
            f"{field} must be 1-{max_length} safe identifier characters",
            details={"field": field},
        )
    return normalized


def validate_optional_identifier(
    value: str | None, field: str, *, max_length: int = 128
) -> str | None:
    if value is None:
        return None
    return validate_identifier(value, field, max_length=max_length)


def validate_currency(value: str) -> str:
    normalized = value.strip().upper()
    if not CURRENCY.fullmatch(normalized):
        raise InvalidRequest("currency must be a three-letter ISO code")
    return normalized


def validate_money(value: Decimal, field: str) -> Decimal:
    if not value.is_finite() or value < 0:
        raise InvalidRequest(f"{field} must be a finite non-negative amount")
    try:
        normalized = value.quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise InvalidRequest(f"{field} is outside the supported range") from exc
    if normalized != value:
        raise InvalidRequest(f"{field} must have no more than two decimal places")
    if normalized >= Decimal("10000000000000000"):
        raise InvalidRequest(f"{field} is outside the supported range")
    return normalized


def validate_reason(value: str, field: str = "reason") -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 2_000:
        raise InvalidRequest(f"{field} must be between 1 and 2000 characters")
    return normalized


def validate_expected_version(value: int) -> int:
    if value < 1:
        raise InvalidRequest("expectedVersion must be at least 1")
    return value


def normalize_items(items: tuple[BookingItem, ...]) -> tuple[BookingItem, ...]:
    if not 1 <= len(items) <= 50:
        raise InvalidRequest("A booking must contain between 1 and 50 items")
    seen: set[str] = set()
    normalized: list[BookingItem] = []
    for item in items:
        seat_id = validate_identifier(item.seat_id, "seatId")
        ticket_type = validate_identifier(item.ticket_type, "ticketType")
        if seat_id in seen:
            raise InvalidRequest(
                f"Duplicate seatId: {seat_id}", details={"seatId": seat_id}
            )
        unit_price = validate_money(item.unit_price, "unitPrice")
        seen.add(seat_id)
        normalized.append(
            BookingItem(
                seat_id=seat_id,
                ticket_type=ticket_type,
                unit_price=unit_price,
            )
        )
    return tuple(sorted(normalized, key=lambda item: item.seat_id))


def normalize_new_booking(
    *,
    customer_id: str,
    event_id: str,
    reservation_id: str | None,
    payment_method: str | None,
    items: tuple[BookingItem, ...],
    total_amount: Decimal | None,
    currency: str,
) -> NewBookingRequest:
    normalized_items = normalize_items(items)
    calculated_total = sum(
        (item.unit_price for item in normalized_items), Decimal("0.00")
    )
    if total_amount is not None:
        declared = validate_money(total_amount, "totalAmount")
        if declared != calculated_total:
            raise InvalidRequest(
                "totalAmount must equal the sum of booking item prices",
                details={
                    "declaredTotal": str(declared),
                    "calculatedTotal": str(calculated_total),
                },
            )
    return NewBookingRequest(
        customer_id=validate_identifier(customer_id, "customerId"),
        event_id=validate_identifier(event_id, "eventId"),
        reservation_id=validate_optional_identifier(
            reservation_id, "reservationId"
        ),
        payment_method=validate_optional_identifier(
            payment_method, "paymentMethod", max_length=40
        ),
        items=normalized_items,
        total_amount=calculated_total,
        currency=validate_currency(currency),
    )


def validate_ticket_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    if not 1 <= len(values) <= 50:
        raise InvalidRequest("A booking must attach between 1 and 50 ticket ids")
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        ticket_id = validate_identifier(value, "ticketId")
        if ticket_id in seen:
            raise InvalidRequest(
                f"Duplicate ticketId: {ticket_id}", details={"ticketId": ticket_id}
            )
        seen.add(ticket_id)
        normalized.append(ticket_id)
    return tuple(normalized)


def ensure_transition_allowed(current: BookingStatus, target: BookingStatus) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidStateTransition(current.value, target.value)


def canonical_request_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def advisory_lock_id(scope: str, key: str) -> int:
    digest = hashlib.blake2b(f"{scope}:{key}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value.normalize(), "f")
    raise TypeError(f"Unsupported value in canonical payload: {type(value)!r}")
