from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.application.service import PaymentService
from app.domain.enums import PaymentStatus
from app.domain.exceptions import (
    BookingPaymentConflict,
    IdempotencyConflict,
    ProviderReferenceConflict,
)
from app.domain.value_objects import RequestContext
from app.infrastructure.database.models import (
    OutboxEventModel,
    PaymentAuditModel,
    RefundModel,
)

pytestmark = pytest.mark.integration


def context(value: str = "COR-1") -> RequestContext:
    return RequestContext(value, "payment-orchestrator", "USER-1")


def create(
    service: PaymentService,
    *,
    key: str = "CREATE-1",
    booking_id: str = "BK00000001",
    customer_id: str = "C001",
):
    return service.create(
        context(),
        idempotency_key=key,
        booking_id=booking_id,
        customer_id=customer_id,
        amount=Decimal("240.00"),
        currency="VND",
        payment_method="CARD_TOKEN",
        provider="sandbox-provider",
    )


def counts(service: PaymentService) -> tuple[int, int, int]:
    with service.session_factory() as session:
        return (
            int(
                session.scalar(select(func.count()).select_from(PaymentAuditModel)) or 0
            ),
            int(
                session.scalar(select(func.count()).select_from(OutboxEventModel)) or 0
            ),
            int(session.scalar(select(func.count()).select_from(RefundModel)) or 0),
        )


def test_full_lifecycle_is_persistent_audited_and_idempotent(
    service: PaymentService,
) -> None:
    original = create(service)
    replay = create(service)
    assert replay.payment_id == original.payment_id
    assert counts(service) == (1, 1, 0)

    authorized = service.authorize(
        context("COR-2"),
        idempotency_key="AUTHORIZE-1",
        payment_id=original.payment_id,
        approved=True,
        provider_reference="txn-001",
        failure_code=None,
        reason=None,
        expected_version=1,
    )
    assert authorized.status == PaymentStatus.AUTHORIZED

    captured = service.capture(
        context("COR-3"),
        idempotency_key="CAPTURE-1",
        payment_id=original.payment_id,
        succeeded=True,
        provider_reference="txn-001",
        failure_code=None,
        reason=None,
        expected_version=2,
    )
    assert captured.status == PaymentStatus.CAPTURED
    assert captured.captured_amount == Decimal("240.00")

    # A caller that lost the first key can retry the same terminal outcome.
    capture_retry = service.capture(
        context("COR-4"),
        idempotency_key="CAPTURE-2",
        payment_id=original.payment_id,
        succeeded=True,
        provider_reference="txn-001",
        failure_code=None,
        reason=None,
        expected_version=2,
    )
    assert capture_retry.resource_version == 3
    assert counts(service) == (3, 3, 0)

    partial = service.refund(
        context("COR-5"),
        idempotency_key="REFUND-1",
        payment_id=original.payment_id,
        amount=Decimal("40.00"),
        reason="seat downgrade",
        provider_refund_reference="refund-001",
        expected_version=3,
    )
    assert partial.status == PaymentStatus.PARTIALLY_REFUNDED

    refund_retry = service.refund(
        context("COR-6"),
        idempotency_key="REFUND-1-RETRY",
        payment_id=original.payment_id,
        amount=Decimal("40.00"),
        reason="seat downgrade",
        provider_refund_reference="refund-001",
        expected_version=3,
    )
    assert refund_retry.resource_version == 4
    assert counts(service) == (4, 4, 1)

    refunded = service.refund(
        context("COR-7"),
        idempotency_key="REFUND-2",
        payment_id=original.payment_id,
        amount=Decimal("200.00"),
        reason="event cancelled",
        provider_refund_reference="refund-002",
        expected_version=4,
    )
    assert refunded.status == PaymentStatus.REFUNDED
    assert refunded.refunded_amount == refunded.captured_amount
    assert len(service.refunds(original.payment_id)) == 2
    assert counts(service) == (5, 5, 2)


def test_idempotency_and_booking_conflicts_are_distinguished(
    service: PaymentService,
) -> None:
    create(service)
    with pytest.raises(IdempotencyConflict):
        create(service, key="CREATE-1", booking_id="BK00000002")
    with pytest.raises(BookingPaymentConflict):
        create(service, key="CREATE-2", customer_id="C999")


def test_database_rejects_an_inconsistent_aggregate_state(
    service: PaymentService,
) -> None:
    original = create(service)
    with pytest.raises(IntegrityError):
        with service.session_factory() as session:
            with session.begin():
                session.execute(
                    text(
                        "UPDATE payment.payments SET captured_amount = amount "
                        "WHERE payment_id = :payment_id"
                    ),
                    {"payment_id": original.payment_id},
                )


def test_provider_transaction_cannot_be_attached_to_two_payments(
    service: PaymentService,
) -> None:
    first = create(service)
    second = create(
        service,
        key="CREATE-2",
        booking_id="BK00000002",
        customer_id="C002",
    )
    service.authorize(
        context("COR-2"),
        idempotency_key="AUTHORIZE-1",
        payment_id=first.payment_id,
        approved=True,
        provider_reference="txn-shared",
        failure_code=None,
        reason=None,
        expected_version=1,
    )
    with pytest.raises(ProviderReferenceConflict):
        service.authorize(
            context("COR-3"),
            idempotency_key="AUTHORIZE-2",
            payment_id=second.payment_id,
            approved=True,
            provider_reference="txn-shared",
            failure_code=None,
            reason=None,
            expected_version=1,
        )


@pytest.mark.concurrency
def test_concurrent_create_for_one_booking_creates_one_aggregate(
    service: PaymentService,
) -> None:
    def worker(index: int) -> str:
        return create(service, key=f"CONCURRENT-{index}").payment_id

    with ThreadPoolExecutor(max_workers=8) as pool:
        payment_ids = list(pool.map(worker, range(16)))

    assert len(set(payment_ids)) == 1
    assert counts(service) == (1, 1, 0)
    page = service.list(
        page=1,
        page_size=20,
        booking_id=None,
        customer_id=None,
        provider=None,
        status=None,
        search=None,
    )
    assert page.total == 1


def test_mock_timeout_becomes_unknown_then_reconciles_from_final_provider_event(
    service: PaymentService,
) -> None:
    payment = service.create(
        context("COR-TIMEOUT-1"),
        idempotency_key="CREATE-TIMEOUT-1",
        booking_id="BK-TIMEOUT-1",
        customer_id="C001",
        amount=Decimal("240.00"),
        currency="VND",
        payment_method="CARD_TOKEN",
        provider="mock-provider",
        method_token="tok_demo_timeout",
    )
    authorized = service.authorize(
        context("COR-TIMEOUT-2"),
        idempotency_key="AUTHORIZE-TIMEOUT-1",
        payment_id=payment.payment_id,
        approved=None,
        provider_status=None,
        provider_reference=None,
        failure_code=None,
        reason=None,
        expected_version=1,
    )
    unknown = service.capture(
        context("COR-TIMEOUT-3"),
        idempotency_key="CAPTURE-TIMEOUT-1",
        payment_id=payment.payment_id,
        succeeded=None,
        provider_status=None,
        provider_reference=None,
        failure_code=None,
        reason=None,
        expected_version=authorized.resource_version,
    )
    assert unknown.status == PaymentStatus.UNKNOWN

    reconciled = service.reconcile(
        context("COR-TIMEOUT-4"),
        idempotency_key="RECONCILE-TIMEOUT-1",
        payment_id=payment.payment_id,
        provider_status=None,
        provider_reference=None,
        provider_refund_reference=None,
        observed_refunded_amount=None,
        failure_code=None,
        reason=None,
        expected_version=unknown.resource_version,
    )
    assert reconciled.status == PaymentStatus.CAPTURED
    assert reconciled.reconciliation_status.value == "COMPLETED"


def test_provider_callback_is_deduplicated_by_event_id(
    service: PaymentService,
) -> None:
    from datetime import UTC, datetime

    from app.domain.enums import ProviderOperation
    from app.domain.exceptions import IdempotencyConflict

    payment = create(service, booking_id="BK-CALLBACK-1")
    arguments = {
        "event_id": "provider-event-1",
        "payment_id": payment.payment_id,
        "provider": "sandbox-provider",
        "operation": ProviderOperation.AUTHORIZE,
        "provider_status": PaymentStatus.AUTHORIZED,
        "provider_reference": "txn-callback-1",
        "provider_refund_reference": None,
        "amount": Decimal("240.00"),
        "currency": "VND",
        "observed_refunded_amount": None,
        "failure_code": None,
        "reason": None,
        "occurred_at": datetime.now(UTC),
        "payload_hash": "a" * 64,
    }
    first = service.provider_callback(context("COR-CALLBACK-1"), **arguments)
    replay = service.provider_callback(context("COR-CALLBACK-2"), **arguments)
    assert first.resource_version == 2
    assert replay.resource_version == 2
    assert len(service.provider_events(payment.payment_id)) == 1

    with pytest.raises(IdempotencyConflict):
        service.provider_callback(
            context("COR-CALLBACK-3"),
            **{**arguments, "payload_hash": "b" * 64},
        )


def test_create_payment_rejects_amount_that_differs_from_booking_evidence(
    service: PaymentService,
) -> None:
    from app.domain.exceptions import PaymentAmountMismatch
    from app.domain.value_objects import BookingPaymentEvidence

    evidence = BookingPaymentEvidence.from_request(
        booking_id="BK-EVIDENCE-1",
        customer_id="C001",
        amount=Decimal("300.00"),
        currency="VND",
        resource_version=2,
        evidence_id="booking-snapshot-1",
    )
    with pytest.raises(PaymentAmountMismatch):
        service.create(
            context("COR-EVIDENCE-1"),
            idempotency_key="CREATE-EVIDENCE-1",
            booking_id="BK-EVIDENCE-1",
            customer_id="C001",
            amount=Decimal("240.00"),
            currency="VND",
            payment_method="CARD_TOKEN",
            provider="sandbox-provider",
            booking_evidence=evidence,
        )


def test_reconcile_unavailable_persists_attempt_and_backoff_before_503(
    service: PaymentService,
) -> None:
    from app.domain.exceptions import ProviderUnavailable

    payment = create(service, booking_id="BK-UNKNOWN-1")
    authorized = service.authorize(
        context("COR-UNKNOWN-2"),
        idempotency_key="AUTHORIZE-UNKNOWN-1",
        payment_id=payment.payment_id,
        approved=True,
        provider_status=None,
        provider_reference="txn-unknown-1",
        failure_code=None,
        reason=None,
        expected_version=1,
    )
    unknown = service.capture(
        context("COR-UNKNOWN-3"),
        idempotency_key="CAPTURE-UNKNOWN-1",
        payment_id=payment.payment_id,
        succeeded=None,
        provider_status=PaymentStatus.UNKNOWN,
        provider_reference="txn-unknown-1",
        failure_code=None,
        reason="provider response lost",
        expected_version=authorized.resource_version,
    )
    with pytest.raises(ProviderUnavailable):
        service.reconcile(
            context("COR-UNKNOWN-4"),
            idempotency_key="RECONCILE-UNKNOWN-1",
            payment_id=payment.payment_id,
            provider_status=None,
            provider_reference=None,
            provider_refund_reference=None,
            observed_refunded_amount=None,
            failure_code=None,
            reason=None,
            expected_version=unknown.resource_version,
        )

    persisted = service.get(payment.payment_id)
    assert persisted.status == PaymentStatus.UNKNOWN
    assert persisted.reconciliation_attempts == 1
    assert persisted.reconciliation_status.value == "FAILED"
    assert persisted.reconciliation_due_at > persisted.last_reconciled_at
