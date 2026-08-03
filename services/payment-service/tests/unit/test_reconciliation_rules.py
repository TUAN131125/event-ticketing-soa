from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.application.commands.reconcile_payment import (
    _is_noop,
    _validate_outcome_fields,
)
from app.domain.entities import Payment
from app.domain.enums import PaymentStatus
from app.domain.exceptions import InvalidRequest


def captured_payment() -> Payment:
    result = Payment.create(
        payment_id="PAY00000001",
        booking_id="BK00000001",
        customer_id="C001",
        amount=Decimal("240.00"),
        currency="VND",
        payment_method="CARD_TOKEN",
        provider="sandbox-provider",
        now=datetime.now(UTC),
    )
    result.authorize(
        provider_reference="txn-001",
        expected_version=1,
        now=datetime.now(UTC),
    )
    result.capture(
        provider_reference="txn-001",
        expected_version=2,
        now=datetime.now(UTC),
    )
    return result


def test_reconciliation_rejects_fields_unrelated_to_success_outcome() -> None:
    with pytest.raises(InvalidRequest, match="unrelated"):
        _validate_outcome_fields(
            provider_status=PaymentStatus.CAPTURED,
            provider_reference="txn-001",
            provider_refund_reference=None,
            observed_refunded_amount=None,
            failure_code=None,
            reason="unexpected reason",
        )


def test_stale_authorization_is_noop_after_capture_when_reference_matches() -> None:
    result = captured_payment()
    assert _is_noop(
        result,
        provider_status=PaymentStatus.AUTHORIZED,
        provider_reference="txn-001",
        observed_refunded_amount=None,
        failure_code=None,
        reason=None,
    )
    with pytest.raises(InvalidRequest, match="reference"):
        _is_noop(
            result,
            provider_status=PaymentStatus.AUTHORIZED,
            provider_reference="txn-other",
            observed_refunded_amount=None,
            failure_code=None,
            reason=None,
        )


def test_duplicate_failure_must_match_recorded_details() -> None:
    result = Payment.create(
        payment_id="PAY00000002",
        booking_id="BK00000002",
        customer_id="C001",
        amount=Decimal("240.00"),
        currency="VND",
        payment_method="CARD_TOKEN",
        provider="sandbox-provider",
        now=datetime.now(UTC),
    )
    result.fail(
        failure_code="DECLINED",
        reason="issuer declined",
        provider_reference=None,
        expected_version=1,
        now=datetime.now(UTC),
    )
    with pytest.raises(InvalidRequest, match="failure outcome"):
        _is_noop(
            result,
            provider_status=PaymentStatus.FAILED,
            provider_reference=None,
            observed_refunded_amount=None,
            failure_code="DECLINED",
            reason="a different reason",
        )
