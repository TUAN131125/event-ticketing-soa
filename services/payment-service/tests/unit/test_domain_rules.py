from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.domain.entities import Payment
from app.domain.enums import PaymentStatus, RefundKind
from app.domain.exceptions import (
    InvalidRequest,
    InvalidStateTransition,
    ProviderReferenceConflict,
    VersionConflict,
)
from app.domain.rules import advisory_lock_id, canonical_request_hash


def payment() -> Payment:
    return Payment.create(
        payment_id="PAY00000001",
        booking_id="BK00000001",
        customer_id="C001",
        amount=Decimal("240.00"),
        currency="vnd",
        payment_method="CARD_TOKEN",
        provider="sandbox-provider",
        now=datetime.now(UTC),
    )


def test_create_normalizes_money_currency_and_initial_state() -> None:
    result = payment()
    assert result.currency == "VND"
    assert result.amount == Decimal("240.00")
    assert result.captured_amount == Decimal("0.00")
    assert result.refunded_amount == Decimal("0.00")
    assert result.status == PaymentStatus.PENDING
    assert result.resource_version == 1


def test_authorize_capture_and_partial_then_full_refund() -> None:
    result = payment()
    now = datetime.now(UTC)
    result.authorize(provider_reference="txn-001", expected_version=1, now=now)
    assert result.status == PaymentStatus.AUTHORIZED
    assert result.resource_version == 2

    result.capture(provider_reference="txn-001", expected_version=2, now=now)
    assert result.status == PaymentStatus.CAPTURED
    assert result.captured_amount == Decimal("240.00")

    first = result.refund(
        refund_id="RF000000001",
        amount=Decimal("40.00"),
        reason="seat downgrade",
        provider_reference="refund-001",
        kind=RefundKind.REQUESTED,
        expected_version=3,
        now=now,
    )
    assert first.amount == Decimal("40.00")
    assert result.status == PaymentStatus.PARTIALLY_REFUNDED
    assert result.refunded_amount == Decimal("40.00")

    result.refund(
        refund_id="RF000000002",
        amount=Decimal("200.00"),
        reason="event cancelled",
        provider_reference="refund-002",
        kind=RefundKind.REQUESTED,
        expected_version=4,
        now=now,
    )
    assert result.status == PaymentStatus.REFUNDED
    assert result.refunded_amount == result.captured_amount
    assert result.refunded_at == now


def test_capture_requires_authorization_outside_reconciliation() -> None:
    with pytest.raises(InvalidRequest, match="authorized"):
        payment().capture(
            provider_reference="txn-001",
            expected_version=1,
            now=datetime.now(UTC),
        )


def test_over_refund_and_refund_before_capture_are_rejected() -> None:
    result = payment()
    with pytest.raises(InvalidStateTransition):
        result.refund(
            refund_id="RF000000001",
            amount=Decimal("1.00"),
            reason="not captured",
            provider_reference="refund-001",
            kind=RefundKind.REQUESTED,
            expected_version=1,
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
    with pytest.raises(InvalidRequest, match="unrefunded"):
        result.refund(
            refund_id="RF000000002",
            amount=Decimal("240.01"),
            reason="too much",
            provider_reference="refund-002",
            kind=RefundKind.REQUESTED,
            expected_version=3,
            now=datetime.now(UTC),
        )


def test_provider_reference_and_expected_version_cannot_be_overwritten() -> None:
    result = payment()
    result.authorize(
        provider_reference="txn-001",
        expected_version=1,
        now=datetime.now(UTC),
    )
    with pytest.raises(ProviderReferenceConflict):
        result.capture(
            provider_reference="txn-002",
            expected_version=2,
            now=datetime.now(UTC),
        )
    with pytest.raises(VersionConflict):
        result.capture(
            provider_reference="txn-001",
            expected_version=99,
            now=datetime.now(UTC),
        )


def test_domain_rejects_values_that_do_not_fit_persistence_contract() -> None:
    with pytest.raises(InvalidRequest):
        Payment.create(
            payment_id="PAY00000002",
            booking_id="BK00000002",
            customer_id="C001",
            amount=Decimal("10.001"),
            currency="VND",
            payment_method="CARD_TOKEN",
            provider="sandbox-provider",
            now=datetime.now(UTC),
        )
    with pytest.raises(InvalidRequest, match="card data"):
        Payment.create(
            payment_id="PAY00000004",
            booking_id="BK00000004",
            customer_id="C001",
            amount=Decimal("10.00"),
            currency="VND",
            payment_method="4111111111111111",
            provider="sandbox-provider",
            now=datetime.now(UTC),
        )
    with pytest.raises(InvalidRequest):
        Payment.create(
            payment_id="PAY00000003",
            booking_id="BK00000003",
            customer_id="C001",
            amount=Decimal("10000000000000000"),
            currency="VND",
            payment_method="CARD_TOKEN",
            provider="sandbox-provider",
            now=datetime.now(UTC),
        )


def test_hash_and_lock_are_deterministic() -> None:
    assert canonical_request_hash({"b": 2, "a": 1}) == canonical_request_hash(
        {"a": 1, "b": 2}
    )
    assert canonical_request_hash({"amount": Decimal("1.0")}) == (
        canonical_request_hash({"amount": Decimal("1.00")})
    )
    assert advisory_lock_id("CreatePayment", "key-1") == advisory_lock_id(
        "CreatePayment", "key-1"
    )
    assert advisory_lock_id("CreatePayment", "key-1") != advisory_lock_id(
        "CreatePayment", "key-2"
    )
