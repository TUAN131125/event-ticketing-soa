from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.domain.enums import PaymentStatus, ProviderOperation
from app.schemas.requests import (
    AuthorizePaymentRequest,
    CreatePaymentRequest,
    ProviderCallbackRequest,
)


def test_legacy_and_canonical_create_payment_fields_remain_compatible() -> None:
    legacy = CreatePaymentRequest.model_validate(
        {
            "bookingId": "BKG-1",
            "customerId": "CUS-1",
            "amount": "1500000.00",
            "currency": "VND",
            "paymentMethod": "CARD_TOKEN",
            "provider": "mock-provider",
        }
    )
    canonical = CreatePaymentRequest.model_validate(
        {
            "bookingId": "BKG-1",
            "customerId": "CUS-1",
            "amountMinor": 1500000,
            "currency": "VND",
            "methodToken": "tok_demo_success",
        }
    )
    assert legacy.resolved_amount() == Decimal("1500000.00")
    assert canonical.resolved_amount() == Decimal("1500000.00")
    assert canonical.resolved_payment_method() == "MOCK_TOKEN"


def test_legacy_authorize_body_and_new_provider_status_are_both_accepted() -> None:
    assert AuthorizePaymentRequest.model_validate(
        {"approved": True, "providerReference": "txn-1", "expectedVersion": 1}
    ).approved is True
    assert (
        AuthorizePaymentRequest.model_validate(
            {"providerStatus": "UNKNOWN", "expectedVersion": 1}
        ).provider_status
        == PaymentStatus.UNKNOWN
    )


def test_callback_money_requires_complete_amount_currency_pair() -> None:
    base = {
        "eventId": "evt-1",
        "paymentId": "PAY-1",
        "provider": "mock-provider",
        "operation": ProviderOperation.CAPTURE,
        "providerStatus": PaymentStatus.CAPTURED,
        "providerReference": "txn-1",
        "occurredAt": "2026-08-06T02:00:00Z",
    }
    with pytest.raises(ValidationError):
        ProviderCallbackRequest.model_validate({**base, "amount": "10.00"})
    with pytest.raises(ValidationError):
        ProviderCallbackRequest.model_validate({**base, "currency": "VND"})
