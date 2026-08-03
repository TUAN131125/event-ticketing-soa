"""Pure payment invariants and deterministic request hashing."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.enums import PaymentStatus
from app.domain.exceptions import InvalidRequest, InvalidStateTransition

IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
CURRENCY = re.compile(r"^[A-Z]{3}$")

ALLOWED_TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    PaymentStatus.PENDING: frozenset(
        {
            PaymentStatus.AUTHORIZED,
            PaymentStatus.CAPTURED,
            PaymentStatus.FAILED,
            PaymentStatus.CANCELLED,
        }
    ),
    PaymentStatus.AUTHORIZED: frozenset(
        {PaymentStatus.CAPTURED, PaymentStatus.FAILED, PaymentStatus.CANCELLED}
    ),
    PaymentStatus.CAPTURED: frozenset(
        {PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED}
    ),
    PaymentStatus.PARTIALLY_REFUNDED: frozenset(
        {PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED}
    ),
    PaymentStatus.FAILED: frozenset(),
    PaymentStatus.CANCELLED: frozenset(),
    PaymentStatus.REFUNDED: frozenset(),
}


def validate_identifier(value: str, field: str, *, max_length: int = 128) -> str:
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


def validate_payment_method(value: str) -> str:
    normalized = validate_identifier(value, "paymentMethod", max_length=40)
    if not any(character.isalpha() for character in normalized):
        raise InvalidRequest(
            "paymentMethod must be a non-sensitive method category, not card data"
        )
    return normalized


def validate_currency(value: str) -> str:
    normalized = value.strip().upper()
    if not CURRENCY.fullmatch(normalized):
        raise InvalidRequest("currency must be a three-letter ISO code")
    return normalized


def validate_money(
    value: Decimal,
    field: str,
    *,
    allow_zero: bool = False,
) -> Decimal:
    if not value.is_finite() or value < 0 or (not allow_zero and value == 0):
        qualifier = "non-negative" if allow_zero else "positive"
        raise InvalidRequest(f"{field} must be a finite {qualifier} amount")
    try:
        normalized = value.quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise InvalidRequest(f"{field} is outside the supported range") from exc
    if normalized != value:
        raise InvalidRequest(f"{field} must have no more than two decimal places")
    if normalized >= Decimal("10000000000000000"):
        raise InvalidRequest(f"{field} is outside the supported range")
    if normalized.is_zero():
        return Decimal("0.00")
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


def ensure_transition_allowed(current: PaymentStatus, target: PaymentStatus) -> None:
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
