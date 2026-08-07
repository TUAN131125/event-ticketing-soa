"""Payment vocabulary is translated in exactly one place, and never guessed at.

Payment Service and Booking Service publish different PaymentStatus enums
(contracts/payment-service.yaml vs contracts/booking-service.yaml). Every value of the
Payment enum must have a defined Booking counterpart, and anything outside the enum must be
a protocol error rather than a silent failure.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.domain.errors import EsbError
from app.domain.models import PaymentStatus
from app.domain.payment_status import (
    is_captured,
    is_failed,
    is_pending,
    parse_payment_status,
    to_booking_payment_status,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]

EXPECTED_MAPPING = {
    PaymentStatus.PENDING: "PENDING",
    PaymentStatus.AUTHORIZED: "PROCESSING",
    PaymentStatus.CAPTURED: "SUCCEEDED",
    PaymentStatus.UNKNOWN: "UNKNOWN",
    PaymentStatus.FAILED: "FAILED",
    PaymentStatus.CANCELLED: "FAILED",
    PaymentStatus.PARTIALLY_REFUNDED: "REFUND_PENDING",
    PaymentStatus.REFUNDED: "REFUNDED",
}


def canonical_enum(document: str, schema: str) -> set[str]:
    path = REPOSITORY_ROOT / "contracts" / document
    return set(
        yaml.safe_load(path.read_text(encoding="utf-8"))["components"]["schemas"][schema][
            "enum"
        ]
    )


def test_esb_enum_matches_the_payment_canonical_enum() -> None:
    assert {status.value for status in PaymentStatus} == canonical_enum(
        "payment-service.yaml", "PaymentStatus"
    )


def test_every_payment_status_maps_into_the_booking_enum() -> None:
    booking_enum = canonical_enum("booking-service.yaml", "PaymentStatus")
    for status in PaymentStatus:
        assert to_booking_payment_status(status) in booking_enum


@pytest.mark.parametrize(("status", "expected"), sorted(EXPECTED_MAPPING.items()))
def test_mapping_is_exhaustive_and_stable(status: PaymentStatus, expected: str) -> None:
    assert to_booking_payment_status(status) == expected


def test_captured_becomes_succeeded() -> None:
    assert to_booking_payment_status(PaymentStatus.CAPTURED) == "SUCCEEDED"


def test_unknown_stays_unknown_and_is_never_settled() -> None:
    assert to_booking_payment_status(PaymentStatus.UNKNOWN) == "UNKNOWN"
    assert is_pending(PaymentStatus.UNKNOWN)
    assert not is_failed(PaymentStatus.UNKNOWN)
    assert not is_captured(PaymentStatus.UNKNOWN)


def test_partial_refund_is_not_a_completed_refund() -> None:
    assert to_booking_payment_status(PaymentStatus.PARTIALLY_REFUNDED) == "REFUND_PENDING"
    assert to_booking_payment_status(PaymentStatus.REFUNDED) == "REFUNDED"


def test_only_failed_and_cancelled_are_authoritative_failures() -> None:
    assert {status for status in PaymentStatus if is_failed(status)} == {
        PaymentStatus.FAILED,
        PaymentStatus.CANCELLED,
    }


@pytest.mark.parametrize("status", sorted(s.value for s in PaymentStatus))
def test_parse_accepts_every_canonical_status(status: str) -> None:
    assert parse_payment_status({"status": status}) is PaymentStatus(status)


def test_parse_normalises_case_and_padding() -> None:
    assert parse_payment_status({"status": " captured "}) is PaymentStatus.CAPTURED


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"status": None},
        {"status": ""},
        {"status": "DECLINED"},
        {"status": "SUCCEEDED"},
        {"status": 12},
    ],
)
def test_unreadable_status_is_a_protocol_error_not_a_failure(payload: dict) -> None:
    """DECLINED and SUCCEEDED belong to other services' vocabularies, not Payment's."""
    with pytest.raises(EsbError) as raised:
        parse_payment_status(payload)
    assert raised.value.code == "PAYMENT_PROTOCOL_ERROR"
    assert raised.value.status_code == 502
    assert raised.value.retryable is False
