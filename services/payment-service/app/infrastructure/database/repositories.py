"""PostgreSQL primitives used by payment command/query handlers."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.domain.entities import Payment
from app.domain.enums import (
    MockProviderScenario,
    PaymentEventType,
    PaymentStatus,
    ProviderOperation,
    ProviderOutcomeSource,
    ReconciliationStatus,
    RefundKind,
)
from app.domain.value_objects import ProviderEvent, Refund
from app.infrastructure.database.models import (
    IdempotencyRecordModel,
    OutboxEventModel,
    PaymentAuditModel,
    PaymentModel,
    ProviderEventModel,
    RefundModel,
)

LIKE_ESCAPE = "\\"


def contains_pattern(value: str) -> str:
    """Build a LIKE 'contains' pattern that treats the input as literal text.

    Without escaping, a caller sending '%' would match every row and turn a
    filtered lookup into a full scan of the payments table.
    """
    escaped = (
        value.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )
    return f"%{escaped}%"


def set_local_timeouts(
    session: Session, *, lock_timeout_ms: int, statement_timeout_ms: int
) -> None:
    session.execute(
        text("SELECT set_config('lock_timeout', :value, true)"),
        {"value": f"{lock_timeout_ms}ms"},
    )
    session.execute(
        text("SELECT set_config('statement_timeout', :value, true)"),
        {"value": f"{statement_timeout_ms}ms"},
    )


def database_now(session: Session) -> datetime:
    return cast(datetime, session.scalar(select(func.clock_timestamp())))


def acquire_advisory_lock(session: Session, lock_id: int) -> None:
    session.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": lock_id})


def next_payment_id(session: Session) -> str:
    value = session.execute(
        text("SELECT nextval('payment.payment_id_seq')")
    ).scalar_one()
    return f"PAY{int(value):08d}"


def next_refund_id(session: Session) -> str:
    value = session.execute(
        text("SELECT nextval('payment.refund_id_seq')")
    ).scalar_one()
    return f"RF{int(value):09d}"


def get_payment_model(
    session: Session, payment_id: str, *, for_update: bool = False
) -> PaymentModel | None:
    statement = select(PaymentModel).where(PaymentModel.payment_id == payment_id)
    if for_update:
        statement = statement.with_for_update(of=PaymentModel)
    return session.scalar(statement)


def get_payment_by_booking(
    session: Session, booking_id: str, *, for_update: bool = False
) -> PaymentModel | None:
    statement = select(PaymentModel).where(PaymentModel.booking_id == booking_id)
    if for_update:
        statement = statement.with_for_update(of=PaymentModel)
    return session.scalar(statement)


def get_payment_by_provider_reference(
    session: Session,
    provider: str,
    provider_reference: str,
) -> PaymentModel | None:
    return session.scalar(
        select(PaymentModel)
        .where(
            PaymentModel.provider == provider,
            PaymentModel.provider_reference == provider_reference,
        )
        .with_for_update()
    )


def list_payment_models(
    session: Session,
    *,
    page: int,
    page_size: int,
    booking_id: str | None,
    customer_id: str | None,
    provider: str | None,
    status: PaymentStatus | None,
    search: str | None,
) -> tuple[list[PaymentModel], int]:
    filters: list[Any] = []
    if booking_id:
        filters.append(PaymentModel.booking_id == booking_id)
    if customer_id:
        filters.append(PaymentModel.customer_id == customer_id)
    if provider:
        filters.append(PaymentModel.provider == provider)
    if status:
        filters.append(PaymentModel.status == status.value)
    if search:
        value = contains_pattern(search)
        filters.append(
            or_(
                PaymentModel.payment_id.ilike(value, escape=LIKE_ESCAPE),
                PaymentModel.booking_id.ilike(value, escape=LIKE_ESCAPE),
                PaymentModel.customer_id.ilike(value, escape=LIKE_ESCAPE),
                PaymentModel.provider_reference.ilike(value, escape=LIKE_ESCAPE),
            )
        )
    total = int(
        session.scalar(select(func.count()).select_from(PaymentModel).where(*filters))
        or 0
    )
    statement = (
        select(PaymentModel)
        .where(*filters)
        .order_by(PaymentModel.created_at.desc(), PaymentModel.payment_id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(session.scalars(statement).all()), total


def list_refund_models(session: Session, payment_id: str) -> list[RefundModel]:
    return list(
        session.scalars(
            select(RefundModel)
            .where(RefundModel.payment_id == payment_id)
            .order_by(RefundModel.created_at, RefundModel.refund_id)
        ).all()
    )


def get_refund_by_provider_reference(
    session: Session,
    provider: str,
    provider_reference: str,
) -> RefundModel | None:
    return session.scalar(
        select(RefundModel)
        .where(
            RefundModel.provider == provider,
            RefundModel.provider_reference == provider_reference,
        )
        .with_for_update()
    )


def get_provider_event(
    session: Session, event_id: str, *, for_update: bool = False
) -> ProviderEventModel | None:
    statement = select(ProviderEventModel).where(
        ProviderEventModel.event_id == event_id
    )
    if for_update:
        statement = statement.with_for_update(of=ProviderEventModel)
    return session.scalar(statement)


def append_provider_event(session: Session, event: ProviderEvent) -> None:
    session.add(
        ProviderEventModel(
            event_id=event.event_id,
            payment_id=event.payment_id,
            provider=event.provider,
            operation=event.operation.value,
            provider_status=event.status.value,
            source=event.source.value,
            payload_hash=event.payload_hash,
            provider_reference=event.provider_reference,
            provider_refund_reference=event.provider_refund_reference,
            amount=event.amount,
            currency=event.currency,
            observed_refunded_amount=event.refunded_amount,
            failure_code=event.failure_code,
            reason=event.reason,
            occurred_at=event.occurred_at,
            received_at=event.received_at,
        )
    )


def provider_event_model_to_value(model: ProviderEventModel) -> ProviderEvent:
    return ProviderEvent(
        event_id=model.event_id,
        payment_id=model.payment_id,
        provider=model.provider,
        operation=ProviderOperation(model.operation),
        status=PaymentStatus(model.provider_status),
        source=ProviderOutcomeSource(model.source),
        payload_hash=model.payload_hash,
        occurred_at=model.occurred_at,
        received_at=model.received_at,
        provider_reference=model.provider_reference,
        provider_refund_reference=model.provider_refund_reference,
        amount=Decimal(model.amount) if model.amount is not None else None,
        currency=model.currency,
        refunded_amount=(
            Decimal(model.observed_refunded_amount)
            if model.observed_refunded_amount is not None
            else None
        ),
        failure_code=model.failure_code,
        reason=model.reason,
    )


def latest_provider_event(
    session: Session,
    payment_id: str,
    operation: ProviderOperation | None = None,
) -> ProviderEvent | None:
    statement = select(ProviderEventModel).where(
        ProviderEventModel.payment_id == payment_id
    )
    if operation is not None:
        statement = statement.where(
            ProviderEventModel.operation == operation.value
        )
    statement = statement.order_by(
        ProviderEventModel.occurred_at.desc(),
        ProviderEventModel.received_at.desc(),
        ProviderEventModel.event_id.desc(),
    ).limit(1)
    model = session.scalar(statement)
    return provider_event_model_to_value(model) if model else None


def latest_final_provider_event(
    session: Session,
    payment_id: str,
    operation: ProviderOperation | None = None,
) -> ProviderEvent | None:
    """Return the newest final provider outcome, ignoring UNKNOWN markers.

    A timeout flow records both the provider's committed outcome and the local
    UNKNOWN marker. Reconciliation must read the former rather than repeatedly
    selecting the latter.
    """
    statement = select(ProviderEventModel).where(
        ProviderEventModel.payment_id == payment_id,
        ProviderEventModel.provider_status.notin_(
            [PaymentStatus.PENDING.value, PaymentStatus.UNKNOWN.value]
        ),
    )
    if operation is not None:
        statement = statement.where(
            ProviderEventModel.operation == operation.value
        )
    statement = statement.order_by(
        ProviderEventModel.occurred_at.desc(),
        ProviderEventModel.received_at.desc(),
        ProviderEventModel.event_id.desc(),
    ).limit(1)
    model = session.scalar(statement)
    return provider_event_model_to_value(model) if model else None


def list_provider_events(
    session: Session, payment_id: str
) -> tuple[ProviderEvent, ...]:
    models = session.scalars(
        select(ProviderEventModel)
        .where(ProviderEventModel.payment_id == payment_id)
        .order_by(ProviderEventModel.occurred_at, ProviderEventModel.event_id)
    ).all()
    return tuple(provider_event_model_to_value(model) for model in models)


def list_due_unknown_payments(
    session: Session,
    *,
    now: datetime,
    limit: int,
) -> tuple[tuple[str, int], ...]:
    """Claim a bounded batch of UNKNOWN payments due for reconciliation.

    ``SKIP LOCKED`` lets several workers cooperate without choosing the same
    payment in one polling cycle. The command still applies the aggregate row
    lock and optimistic version check before changing state.
    """
    rows = session.execute(
        select(PaymentModel.payment_id, PaymentModel.resource_version)
        .where(
            PaymentModel.status == PaymentStatus.UNKNOWN.value,
            PaymentModel.reconciliation_due_at.is_not(None),
            PaymentModel.reconciliation_due_at <= now,
        )
        .order_by(
            PaymentModel.reconciliation_due_at,
            PaymentModel.payment_id,
        )
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    return tuple((str(payment_id), int(version)) for payment_id, version in rows)


def get_idempotency_record(
    session: Session, scope: str, key: str
) -> IdempotencyRecordModel | None:
    return session.scalar(
        select(IdempotencyRecordModel)
        .where(
            IdempotencyRecordModel.scope == scope,
            IdempotencyRecordModel.idempotency_key == key,
        )
        .with_for_update()
    )


def save_idempotency_record(
    session: Session,
    *,
    scope: str,
    key: str,
    request_hash: str,
    response_body: dict[str, Any],
    resource_id: str,
    now: datetime,
    ttl_seconds: int,
) -> None:
    session.add(
        IdempotencyRecordModel(
            scope=scope,
            idempotency_key=key,
            request_hash=request_hash,
            status="COMPLETED",
            response_body=response_body,
            resource_id=resource_id,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
    )


def append_audit(
    session: Session,
    *,
    payment: Payment,
    operation: str,
    previous_status: PaymentStatus | None,
    caller_service: str,
    actor_id: str | None,
    correlation_id: str,
    idempotency_key: str,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        PaymentAuditModel(
            payment_id=payment.payment_id,
            operation=operation,
            previous_status=previous_status.value if previous_status else None,
            new_status=payment.status.value,
            caller_service=caller_service,
            actor_id=actor_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            resource_version=payment.resource_version,
            details=details or {},
        )
    )


def append_outbox_event(
    session: Session,
    *,
    payment: Payment,
    event_type: PaymentEventType,
    payload: dict[str, Any],
    correlation_id: str,
    now: datetime,
) -> None:
    session.add(
        OutboxEventModel(
            event_id=str(uuid.uuid4()),
            aggregate_id=payment.payment_id,
            aggregate_type="Payment",
            aggregate_version=payment.resource_version,
            event_type=event_type.value,
            payload=payload,
            correlation_id=correlation_id,
            occurred_at=now,
        )
    )


def append_refund(
    session: Session,
    *,
    payment: Payment,
    refund: Refund,
    idempotency_key: str,
) -> None:
    session.add(
        RefundModel(
            refund_id=refund.refund_id,
            payment_id=refund.payment_id,
            provider=payment.provider,
            provider_reference=refund.provider_reference,
            amount=refund.amount,
            currency=refund.currency,
            reason=refund.reason,
            kind=refund.kind.value,
            idempotency_key=idempotency_key,
            created_at=refund.created_at,
        )
    )


def model_to_entity(model: PaymentModel) -> Payment:
    return Payment(
        payment_id=model.payment_id,
        booking_id=model.booking_id,
        customer_id=model.customer_id,
        amount=Decimal(model.amount),
        currency=model.currency,
        payment_method=model.payment_method,
        provider=model.provider,
        status=PaymentStatus(model.status),
        captured_amount=Decimal(model.captured_amount),
        refunded_amount=Decimal(model.refunded_amount),
        resource_version=model.resource_version,
        created_at=model.created_at,
        updated_at=model.updated_at,
        provider_reference=model.provider_reference,
        failure_code=model.failure_code,
        failure_reason=model.failure_reason,
        cancellation_reason=model.cancellation_reason,
        authorized_at=model.authorized_at,
        captured_at=model.captured_at,
        cancelled_at=model.cancelled_at,
        refunded_at=model.refunded_at,
        method_fingerprint=model.method_fingerprint,
        provider_scenario=MockProviderScenario(model.provider_scenario),
        booking_evidence_version=model.booking_evidence_version,
        booking_evidence_id=model.booking_evidence_id,
        booking_evidence_verified=model.booking_evidence_verified,
        last_stable_status=(
            PaymentStatus(model.last_stable_status)
            if model.last_stable_status
            else None
        ),
        pending_operation=(
            ProviderOperation(model.pending_operation)
            if model.pending_operation
            else None
        ),
        reconciliation_status=ReconciliationStatus(model.reconciliation_status),
        reconciliation_attempts=model.reconciliation_attempts,
        unknown_since=model.unknown_since,
        reconciliation_due_at=model.reconciliation_due_at,
        last_reconciled_at=model.last_reconciled_at,
        reconciliation_error=model.reconciliation_error,
    )


def refund_model_to_value(model: RefundModel) -> Refund:
    return Refund(
        refund_id=model.refund_id,
        payment_id=model.payment_id,
        amount=Decimal(model.amount),
        currency=model.currency,
        reason=model.reason,
        kind=RefundKind(model.kind),
        provider_reference=model.provider_reference,
        created_at=model.created_at,
    )


def entity_to_model(payment: Payment) -> PaymentModel:
    return PaymentModel(
        payment_id=payment.payment_id,
        booking_id=payment.booking_id,
        customer_id=payment.customer_id,
        amount=payment.amount,
        currency=payment.currency,
        payment_method=payment.payment_method,
        provider=payment.provider,
        method_fingerprint=payment.method_fingerprint,
        provider_scenario=payment.provider_scenario.value,
        booking_evidence_version=payment.booking_evidence_version,
        booking_evidence_id=payment.booking_evidence_id,
        booking_evidence_verified=payment.booking_evidence_verified,
        provider_reference=payment.provider_reference,
        status=payment.status.value,
        last_stable_status=(
            payment.last_stable_status.value if payment.last_stable_status else None
        ),
        pending_operation=(
            payment.pending_operation.value if payment.pending_operation else None
        ),
        reconciliation_status=payment.reconciliation_status.value,
        reconciliation_attempts=payment.reconciliation_attempts,
        reconciliation_error=payment.reconciliation_error,
        captured_amount=payment.captured_amount,
        refunded_amount=payment.refunded_amount,
        failure_code=payment.failure_code,
        failure_reason=payment.failure_reason,
        cancellation_reason=payment.cancellation_reason,
        resource_version=payment.resource_version,
        created_at=payment.created_at,
        updated_at=payment.updated_at,
        authorized_at=payment.authorized_at,
        captured_at=payment.captured_at,
        cancelled_at=payment.cancelled_at,
        refunded_at=payment.refunded_at,
        unknown_since=payment.unknown_since,
        reconciliation_due_at=payment.reconciliation_due_at,
        last_reconciled_at=payment.last_reconciled_at,
    )


def apply_entity(model: PaymentModel, payment: Payment) -> None:
    model.provider_reference = payment.provider_reference
    model.status = payment.status.value
    model.last_stable_status = (
        payment.last_stable_status.value if payment.last_stable_status else None
    )
    model.pending_operation = (
        payment.pending_operation.value if payment.pending_operation else None
    )
    model.reconciliation_status = payment.reconciliation_status.value
    model.reconciliation_attempts = payment.reconciliation_attempts
    model.reconciliation_error = payment.reconciliation_error
    model.captured_amount = payment.captured_amount
    model.refunded_amount = payment.refunded_amount
    model.failure_code = payment.failure_code
    model.failure_reason = payment.failure_reason
    model.cancellation_reason = payment.cancellation_reason
    model.resource_version = payment.resource_version
    model.updated_at = payment.updated_at
    model.authorized_at = payment.authorized_at
    model.captured_at = payment.captured_at
    model.cancelled_at = payment.cancelled_at
    model.refunded_at = payment.refunded_at
    model.unknown_since = payment.unknown_since
    model.reconciliation_due_at = payment.reconciliation_due_at
    model.last_reconciled_at = payment.last_reconciled_at


def claim_next_outbox_event(
    session: Session, *, max_attempts: int
) -> OutboxEventModel | None:
    """Lock the oldest event still awaiting publication, or return None.

    SKIP LOCKED lets several relay processes share the backlog: each one takes a
    different row instead of queueing behind the same lock. Events that exhausted
    their attempts are left behind for an operator rather than retried forever.
    """
    return session.scalar(
        select(OutboxEventModel)
        .where(
            OutboxEventModel.published_at.is_(None),
            OutboxEventModel.publish_attempts < max_attempts,
        )
        .order_by(OutboxEventModel.occurred_at, OutboxEventModel.event_id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )


def mark_outbox_published(event: OutboxEventModel, now: datetime) -> None:
    event.published_at = now
    event.last_error = None


def mark_outbox_failed(event: OutboxEventModel, error: str) -> None:
    event.publish_attempts += 1
    event.last_error = error[:500]


def count_outbox_backlog(session: Session, *, max_attempts: int) -> tuple[int, int]:
    """Return how many events are still pending and how many gave up retrying."""
    pending = int(
        session.scalar(
            select(func.count())
            .select_from(OutboxEventModel)
            .where(
                OutboxEventModel.published_at.is_(None),
                OutboxEventModel.publish_attempts < max_attempts,
            )
        )
        or 0
    )
    exhausted = int(
        session.scalar(
            select(func.count())
            .select_from(OutboxEventModel)
            .where(
                OutboxEventModel.published_at.is_(None),
                OutboxEventModel.publish_attempts >= max_attempts,
            )
        )
        or 0
    )
    return pending, exhausted


def payment_counts_by_status(session: Session) -> Sequence[tuple[str, int]]:
    return tuple(
        (str(status), int(count))
        for status, count in session.execute(
            select(PaymentModel.status, func.count())
            .group_by(PaymentModel.status)
            .order_by(PaymentModel.status)
        )
    )
