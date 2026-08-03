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
from app.domain.enums import PaymentEventType, PaymentStatus, RefundKind
from app.domain.value_objects import Refund
from app.infrastructure.database.models import (
    IdempotencyRecordModel,
    OutboxEventModel,
    PaymentAuditModel,
    PaymentModel,
    RefundModel,
)


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
        value = f"%{search}%"
        filters.append(
            or_(
                PaymentModel.payment_id.ilike(value),
                PaymentModel.booking_id.ilike(value),
                PaymentModel.customer_id.ilike(value),
                PaymentModel.provider_reference.ilike(value),
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
        provider_reference=payment.provider_reference,
        status=payment.status.value,
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
    )


def apply_entity(model: PaymentModel, payment: Payment) -> None:
    model.provider_reference = payment.provider_reference
    model.status = payment.status.value
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


def payment_counts_by_status(session: Session) -> Sequence[tuple[str, int]]:
    return tuple(
        (str(status), int(count))
        for status, count in session.execute(
            select(PaymentModel.status, func.count())
            .group_by(PaymentModel.status)
            .order_by(PaymentModel.status)
        )
    )
