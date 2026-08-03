"""Pure ticket invariants and deterministic request hashing."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

from app.domain.enums import TicketStatus
from app.domain.exceptions import InvalidRequest, InvalidStateTransition
from app.domain.value_objects import TicketDefinition

IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
ALLOWED_TRANSITIONS: dict[TicketStatus, frozenset[TicketStatus]] = {
    TicketStatus.VALID: frozenset(
        {TicketStatus.VALID, TicketStatus.CHECKED_IN, TicketStatus.CANCELLED}
    ),
    TicketStatus.CHECKED_IN: frozenset(),
    TicketStatus.CANCELLED: frozenset(),
}


def validate_identifier(value: str, field: str, *, max_length: int = 128) -> str:
    normalized = value.strip()
    if not IDENTIFIER.fullmatch(normalized) or len(normalized) > max_length:
        raise InvalidRequest(
            f"{field} must be 1-{max_length} safe identifier characters",
            details={"field": field},
        )
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


def normalize_ticket_definitions(
    values: Iterable[TicketDefinition],
) -> tuple[TicketDefinition, ...]:
    normalized = tuple(
        TicketDefinition(
            seat_id=validate_identifier(value.seat_id, "seatId"),
            seat_label=validate_identifier(value.seat_label, "seatLabel"),
            ticket_type=validate_identifier(value.ticket_type, "ticketType"),
        )
        for value in values
    )
    if not 1 <= len(normalized) <= 50:
        raise InvalidRequest("tickets must contain between 1 and 50 seats")
    seat_ids = [value.seat_id for value in normalized]
    if len(set(seat_ids)) != len(seat_ids):
        raise InvalidRequest("tickets cannot contain duplicate seatId values")
    return tuple(sorted(normalized, key=lambda value: value.seat_id))


def ensure_transition_allowed(current: TicketStatus, target: TicketStatus) -> None:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidStateTransition(current.value, target.value)


def canonical_request_hash(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def advisory_lock_id(scope: str, key: str) -> int:
    digest = hashlib.blake2b(f"{scope}:{key}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big", signed=True)
