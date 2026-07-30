"""Pure domain validation and deterministic request hashing."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from app.domain.exceptions import InvalidRequest

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def validate_identifier(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not IDENTIFIER_PATTERN.fullmatch(normalized):
        raise InvalidRequest(f"{field_name} must be 1-128 safe identifier characters")
    return normalized


def normalize_seat_ids(seat_ids: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(
        sorted({validate_identifier(item, "seatId") for item in seat_ids})
    )
    if not normalized:
        raise InvalidRequest("At least one seatId is required")
    if len(normalized) != len(seat_ids):
        raise InvalidRequest("seatIds must not contain duplicates")
    if len(normalized) > 50:
        raise InvalidRequest("A reservation may contain at most 50 seats")
    return normalized


def validate_hold_seconds(value: int, minimum: int, maximum: int) -> int:
    if not minimum <= value <= maximum:
        raise InvalidRequest(f"holdSeconds must be between {minimum} and {maximum}")
    return value


def validate_extension_seconds(value: int, maximum: int) -> int:
    if not 1 <= value <= maximum:
        raise InvalidRequest(f"extensionSeconds must be between 1 and {maximum}")
    return value


def canonical_request_hash(payload: Mapping[str, Any]) -> str:
    serialized = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=_json_default,
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def advisory_lock_id(scope: str, key: str) -> int:
    digest = hashlib.sha256(f"{scope}:{key}".encode()).digest()[:8]
    return int.from_bytes(digest, byteorder="big", signed=True)


def utc_now() -> datetime:
    return datetime.now(UTC)


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    raise TypeError(f"Unsupported canonical value: {type(value).__name__}")
