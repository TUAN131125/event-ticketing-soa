from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.application.commands.reconcile_payment import (
    _is_noop,
    _validate_outcome_fields,
)
from app.domain.entities import Payment
from app.domain.enums import PaymentStatus, ProviderOperation
from app.domain.exceptions import InvalidRequest
from app.domain.value_objects import PaymentDraft


def new_payment(payment_id: str, booking_id: str) -> Payment:
    return Payment.create(
        payment_id=payment_id,
        draft=PaymentDraft.from_request(
            booking_id=booking_id,
            customer_id="C001",
            amount=Decimal("240.00"),
            currency="VND",
            payment_method="CARD_TOKEN",
            provider="sandbox-provider",
        ),
        now=datetime.now(UTC),
    )


def captured_payment() -> Payment:
    result = new_payment("PAY00000001", "BK00000001")
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
    result = new_payment("PAY00000002", "BK00000002")
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


def test_reconciliation_backoff_is_bounded() -> None:
    from app.application.commands.reconcile_payment import (
        reconciliation_delay_seconds,
    )

    assert reconciliation_delay_seconds(attempts=0, initial=5, maximum=300) == 5
    assert reconciliation_delay_seconds(attempts=3, initial=5, maximum=300) == 40
    assert reconciliation_delay_seconds(attempts=20, initial=5, maximum=300) == 300
    with pytest.raises(ValueError):
        reconciliation_delay_seconds(attempts=-1, initial=5, maximum=300)


def test_exhausted_reconciliation_can_stop_scheduling() -> None:
    now = datetime.now(UTC)
    payment = new_payment("PAY00000003", "BK00000003")
    payment.mark_unknown(
        operation=ProviderOperation.CAPTURE,
        reason="provider response lost",
        expected_version=1,
        now=now,
    )
    payment.record_reconciliation_failure(
        reason="provider unavailable",
        expected_version=2,
        now=now,
        next_due_at=None,
    )
    assert payment.status == PaymentStatus.UNKNOWN
    assert payment.reconciliation_due_at is None
    assert payment.reconciliation_attempts == 1
