"""Shared transaction, idempotency and event-envelope helpers."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.entities import Payment
from app.domain.enums import PaymentEventType, PaymentStatus
from app.domain.exceptions import IdempotencyConflict, ProviderReferenceConflict
from app.domain.rules import advisory_lock_id, validate_identifier
from app.domain.value_objects import RequestContext
from app.infrastructure.database.repositories import (
    acquire_advisory_lock,
    get_idempotency_record,
    get_payment_by_provider_reference,
    save_idempotency_record,
    set_local_timeouts,
)
from app.observability.metrics import IDEMPOTENCY_REPLAY_TOTAL


def validate_context(context: RequestContext, idempotency_key: str) -> str:
    validate_identifier(context.correlation_id, "correlationId")
    validate_identifier(context.caller_service, "callerService")
    if context.actor_id:
        validate_identifier(context.actor_id, "actorId")
    return validate_identifier(idempotency_key, "idempotencyKey")


def prepare_transaction(session: Session, settings: Settings) -> None:
    set_local_timeouts(
        session,
        lock_timeout_ms=settings.db_lock_timeout_ms,
        statement_timeout_ms=settings.db_statement_timeout_ms,
    )


def ensure_payment_provider_reference_available(
    session: Session,
    payment: Payment,
    provider_reference: str | None,
) -> None:
    if provider_reference is None:
        return
    acquire_advisory_lock(
        session,
        advisory_lock_id(
            "PaymentProviderReference",
            f"{payment.provider}:{provider_reference}",
        ),
    )
    existing = get_payment_by_provider_reference(
        session, payment.provider, provider_reference
    )
    if existing is not None and existing.payment_id != payment.payment_id:
        raise ProviderReferenceConflict()


def replay_or_lock(
    session: Session,
    *,
    scope: str,
    key: str,
    request_hash: str,
    now: datetime,
) -> Payment | None:
    acquire_advisory_lock(session, advisory_lock_id(scope, key))
    record = get_idempotency_record(session, scope, key)
    if record is None:
        return None
    if record.expires_at <= now:
        session.delete(record)
        session.flush()
        return None
    if record.request_hash != request_hash:
        raise IdempotencyConflict()
    IDEMPOTENCY_REPLAY_TOTAL.labels(scope).inc()
    return payment_from_payload(record.response_body)


def save_replay(
    session: Session,
    *,
    settings: Settings,
    scope: str,
    key: str,
    request_hash: str,
    payment: Payment,
    now: datetime,
) -> None:
    save_idempotency_record(
        session,
        scope=scope,
        key=key,
        request_hash=request_hash,
        response_body=payment_to_payload(payment),
        resource_id=payment.payment_id,
        now=now,
        ttl_seconds=settings.idempotency_ttl_seconds,
    )


def payment_to_payload(payment: Payment) -> dict[str, Any]:
    return {
        "paymentId": payment.payment_id,
        "bookingId": payment.booking_id,
        "customerId": payment.customer_id,
        "amount": str(payment.amount),
        "currency": payment.currency,
        "paymentMethod": payment.payment_method,
        "provider": payment.provider,
        "providerReference": payment.provider_reference,
        "status": payment.status.value,
        "capturedAmount": str(payment.captured_amount),
        "refundedAmount": str(payment.refunded_amount),
        "failureCode": payment.failure_code,
        "failureReason": payment.failure_reason,
        "cancellationReason": payment.cancellation_reason,
        "resourceVersion": payment.resource_version,
        "createdAt": payment.created_at.isoformat(),
        "updatedAt": payment.updated_at.isoformat(),
        "authorizedAt": (
            payment.authorized_at.isoformat() if payment.authorized_at else None
        ),
        "capturedAt": (
            payment.captured_at.isoformat() if payment.captured_at else None
        ),
        "cancelledAt": (
            payment.cancelled_at.isoformat() if payment.cancelled_at else None
        ),
        "refundedAt": (
            payment.refunded_at.isoformat() if payment.refunded_at else None
        ),
    }


def payment_from_payload(payload: dict[str, Any]) -> Payment:
    return Payment(
        payment_id=str(payload["paymentId"]),
        booking_id=str(payload["bookingId"]),
        customer_id=str(payload["customerId"]),
        amount=Decimal(str(payload["amount"])),
        currency=str(payload["currency"]),
        payment_method=str(payload["paymentMethod"]),
        provider=str(payload["provider"]),
        provider_reference=_optional_text(payload.get("providerReference")),
        status=PaymentStatus(str(payload["status"])),
        captured_amount=Decimal(str(payload["capturedAmount"])),
        refunded_amount=Decimal(str(payload["refundedAmount"])),
        failure_code=_optional_text(payload.get("failureCode")),
        failure_reason=_optional_text(payload.get("failureReason")),
        cancellation_reason=_optional_text(payload.get("cancellationReason")),
        resource_version=int(payload["resourceVersion"]),
        created_at=datetime.fromisoformat(str(payload["createdAt"])),
        updated_at=datetime.fromisoformat(str(payload["updatedAt"])),
        authorized_at=_optional_datetime(payload.get("authorizedAt")),
        captured_at=_optional_datetime(payload.get("capturedAt")),
        cancelled_at=_optional_datetime(payload.get("cancelledAt")),
        refunded_at=_optional_datetime(payload.get("refundedAt")),
    )


def event_payload(payment: Payment) -> dict[str, Any]:
    return {
        "paymentId": payment.payment_id,
        "bookingId": payment.booking_id,
        "customerId": payment.customer_id,
        "status": payment.status.value,
        "amount": str(payment.amount),
        "capturedAmount": str(payment.captured_amount),
        "refundedAmount": str(payment.refunded_amount),
        "currency": payment.currency,
        "paymentMethod": payment.payment_method,
        "provider": payment.provider,
        "providerReference": payment.provider_reference,
        "resourceVersion": payment.resource_version,
        "occurredAt": payment.updated_at.isoformat(),
    }


def event_type_for_status(status: PaymentStatus) -> PaymentEventType:
    mapping = {
        PaymentStatus.AUTHORIZED: PaymentEventType.AUTHORIZED,
        PaymentStatus.CAPTURED: PaymentEventType.SUCCEEDED,
        PaymentStatus.FAILED: PaymentEventType.FAILED,
        PaymentStatus.CANCELLED: PaymentEventType.CANCELLED,
        PaymentStatus.PARTIALLY_REFUNDED: PaymentEventType.REFUNDED,
        PaymentStatus.REFUNDED: PaymentEventType.REFUNDED,
    }
    return mapping[status]


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_datetime(value: Any) -> datetime | None:
    return None if value is None else datetime.fromisoformat(str(value))
