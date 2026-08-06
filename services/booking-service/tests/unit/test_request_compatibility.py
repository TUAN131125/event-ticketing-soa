"""The v1 payloads and the additive v2 evidence payloads normalize identically."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.domain.enums import CompensationStatus, PaymentStatus
from app.schemas.requests import (
    AttachReservationRequest,
    CancelBookingRequest,
    CompensationResultRequest,
    CreateBookingRequest,
    FailBookingRequest,
    RecordPaymentRequest,
)


def test_create_accepts_legacy_numeric_price_contract() -> None:
    request = CreateBookingRequest.model_validate(
        {
            "customerId": "C001",
            "eventId": "EV001",
            "reservationId": "RES-001",
            "paymentMethod": "CARD",
            "items": [
                {"seatId": "A01", "ticketType": "VIP", "unitPrice": 1500000}
            ],
            "totalAmount": 1500000,
            "currency": "vnd",
        }
    )
    assert request.currency == "VND"
    assert request.items[0].ticket_type == "VIP"
    assert request.items[0].unit_price == 1500000


def test_create_accepts_canonical_money_and_ticket_type_code() -> None:
    request = CreateBookingRequest.model_validate(
        {
            "customerId": "C001",
            "eventId": "EV001",
            "items": [
                {
                    "seatId": "A01",
                    "ticketTypeCode": "VIP",
                    "unitPrice": {"amountMinor": 1500000, "currency": "VND"},
                }
            ],
        }
    )
    assert request.currency == "VND"
    assert request.items[0].ticket_type == "VIP"
    assert request.total_amount is None


def test_old_attach_reservation_means_confirmed_evidence() -> None:
    request = AttachReservationRequest.model_validate(
        {
            "reservationId": "RES-001",
            "expectedVersion": 1,
        }
    )
    assert request.resolved_confirmed is True
    assert request.resolved_expires_at is None



def test_mutation_request_accepts_if_match_only_transport_shape() -> None:
    request = AttachReservationRequest.model_validate(
        {
            "reservationId": "RES-001",
            "reservationExpiresAt": "2026-08-06T04:00:00Z",
            "confirmed": False,
        }
    )
    assert request.expected_version is None
    assert request.resolved_confirmed is False

def test_new_attach_reservation_requires_explicit_hold_semantics() -> None:
    expires_at = datetime(2026, 8, 6, 4, 0, tzinfo=UTC)
    request = AttachReservationRequest.model_validate(
        {
            "reservationId": "RES-001",
            "expectedVersion": 1,
            "reservationVersion": 2,
            "reservationExpiresAt": expires_at.isoformat(),
            "confirmed": False,
        }
    )
    assert request.resolved_confirmed is False
    assert request.resolved_expires_at == expires_at


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"succeeded": True}, PaymentStatus.SUCCEEDED),
        ({"succeeded": False}, PaymentStatus.FAILED),
        ({"paymentStatus": "CAPTURED"}, PaymentStatus.SUCCEEDED),
        ({"paymentStatus": "DECLINED"}, PaymentStatus.FAILED),
        ({"paymentStatus": "PENDING_RECONCILIATION"}, PaymentStatus.UNKNOWN),
    ],
)
def test_old_and_new_payment_outcomes_normalize(
    payload: dict[str, object], expected: PaymentStatus
) -> None:
    request = RecordPaymentRequest.model_validate(
        {"paymentId": "PAY-001", "expectedVersion": 3, **payload}
    )
    assert request.resolved_status == expected


def test_conflicting_payment_outcomes_are_rejected() -> None:
    with pytest.raises(ValidationError):
        RecordPaymentRequest.model_validate(
            {
                "paymentId": "PAY-001",
                "expectedVersion": 3,
                "succeeded": True,
                "paymentStatus": "FAILED",
            }
        )


def test_old_failure_and_new_compensation_requests_remain_available() -> None:
    old_failure = FailBookingRequest.model_validate(
        {
            "reasonCode": "PAYMENT_DECLINED",
            "expectedVersion": 4,
        }
    )
    assert old_failure.failure_code == "PAYMENT_DECLINED"
    assert old_failure.reason == "PAYMENT_DECLINED"

    new_result = CompensationResultRequest.model_validate(
        {
            "expectedVersion": 5,
            "compensationStatus": "COMPLETED",
            "evidence": {
                "reservationReleased": True,
                "paymentRefunded": True,
                "resolvedPaymentStatus": "REFUNDED",
            },
        }
    )
    assert new_result.compensation_status == CompensationStatus.COMPLETED
    assert new_result.evidence.resolved_payment_status == PaymentStatus.REFUNDED


def test_cancel_rejects_unknown_fields_to_keep_contract_closed() -> None:
    with pytest.raises(ValidationError):
        CancelBookingRequest.model_validate(
            {
                "reason": "customer request",
                "expectedVersion": 2,
                "unexpectedField": True,
            }
        )
