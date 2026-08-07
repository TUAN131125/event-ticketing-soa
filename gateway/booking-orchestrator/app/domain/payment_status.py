"""The single place Payment Service vocabulary is read and translated.

Payment Service and Booking Service deliberately use different enumerations
(contracts/payment-service.yaml vs contracts/booking-service.yaml). Every translation
between them lives here so a status is never classified by an ad-hoc string comparison
scattered through the saga.

The rule that matters most: a status this module does not recognise is a **provider protocol
error**, never a silent failure. Treating an unreadable payment outcome as "failed" would
release seats and fail a booking that may in fact have been charged.
"""

from __future__ import annotations

from typing import Any

from app.domain.errors import EsbError
from app.domain.models import PaymentStatus

# tns PaymentStatus in contracts/payment-service.yaml.
CANONICAL_PAYMENT_STATUSES: frozenset[str] = frozenset(
    status.value for status in PaymentStatus
)

# Booking Service's own PaymentStatus enum (contracts/booking-service.yaml). Payment has no
# SUCCEEDED and Booking has no CAPTURED/AUTHORIZED, so the two vocabularies are bridged
# explicitly rather than by string identity.
_BOOKING_PAYMENT_STATUS: dict[PaymentStatus, str] = {
    PaymentStatus.PENDING: "PENDING",
    PaymentStatus.AUTHORIZED: "PROCESSING",
    PaymentStatus.CAPTURED: "SUCCEEDED",
    PaymentStatus.UNKNOWN: "UNKNOWN",
    PaymentStatus.FAILED: "FAILED",
    PaymentStatus.CANCELLED: "FAILED",
    # A partial refund is money still partly held: it is a refund in progress, never a
    # completed one.
    PaymentStatus.PARTIALLY_REFUNDED: "REFUND_PENDING",
    PaymentStatus.REFUNDED: "REFUNDED",
}

# Outcome classes the saga branches on.
PENDING_STATUSES: frozenset[PaymentStatus] = frozenset(
    {PaymentStatus.PENDING, PaymentStatus.UNKNOWN}
)
FAILED_STATUSES: frozenset[PaymentStatus] = frozenset(
    {PaymentStatus.FAILED, PaymentStatus.CANCELLED}
)
REFUND_STATUSES: frozenset[PaymentStatus] = frozenset(
    {PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED}
)


def parse_payment_status(payload: dict[str, Any]) -> PaymentStatus:
    """Read the status a Payment response is required to carry.

    There is no default. A missing status, or one outside the canonical enumeration, means
    Payment broke its own contract; that is a non-retryable protocol error, because the same
    response would be just as unreadable on a second attempt.
    """
    raw = payload.get("status")
    if isinstance(raw, str):
        normalised = raw.strip().upper()
        if normalised in CANONICAL_PAYMENT_STATUSES:
            return PaymentStatus(normalised)
    raise EsbError(
        "PAYMENT_PROTOCOL_ERROR",
        "Payment Service returned a payment without a valid status",
        502,
        False,
    )


def to_booking_payment_status(status: PaymentStatus) -> str:
    """Translate a Payment status into the Booking Service vocabulary."""
    try:
        return _BOOKING_PAYMENT_STATUS[status]
    except KeyError as exc:  # pragma: no cover - guarded by the enum itself
        raise EsbError(
            "PAYMENT_PROTOCOL_ERROR",
            "Payment status cannot be expressed to Booking Service",
            502,
            False,
        ) from exc


def is_pending(status: PaymentStatus) -> bool:
    """Outcome not yet authoritative; the saga must not settle on it."""
    return status in PENDING_STATUSES


def is_failed(status: PaymentStatus) -> bool:
    """Authoritatively not paid; compensation may release seats."""
    return status in FAILED_STATUSES


def is_captured(status: PaymentStatus) -> bool:
    return status is PaymentStatus.CAPTURED
