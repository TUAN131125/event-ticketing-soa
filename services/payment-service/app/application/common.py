"""Shared transaction, idempotency and event-envelope helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.domain.entities import Payment
from app.domain.enums import (
    MockProviderScenario,
    PaymentEventType,
    PaymentStatus,
    ProviderOperation,
    ReconciliationStatus,
)
from app.domain.exceptions import (
    IdempotencyConflict,
    InvalidRequest,
    PaymentNotFound,
    ProviderReferenceConflict,
)
from app.domain.rules import advisory_lock_id, validate_identifier
from app.domain.value_objects import Refund, RequestContext
from app.infrastructure.database.models import PaymentModel, RefundModel
from app.infrastructure.database.repositories import (
    acquire_advisory_lock,
    append_audit,
    append_outbox_event,
    database_now,
    get_idempotency_record,
    get_payment_by_provider_reference,
    get_payment_model,
    get_refund_by_provider_reference,
    model_to_entity,
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


@dataclass(frozen=True, slots=True)
class CommandScope:
    """Everything a command handler needs while its transaction is open.

    Every command used to thread these seven values by hand through its audit,
    outbox and idempotency calls, which is why those call sites kept drifting
    apart. Passing the scope keeps one spelling of "finish this command".
    """

    session: Session
    settings: Settings
    context: RequestContext
    scope: str
    key: str
    request_hash: str
    now: datetime

    def replay(self, payment: Payment) -> Payment:
        """Store this key's result for an unchanged payment, then return it.

        Used when the requested outcome is already recorded: the caller retried
        with a new key, so the payment must not advance again.
        """
        save_replay(
            self.session,
            settings=self.settings,
            scope=self.scope,
            key=self.key,
            request_hash=self.request_hash,
            payment=payment,
            now=self.now,
        )
        return payment

    def record(
        self,
        payment: Payment,
        *,
        previous_status: PaymentStatus | None,
        event_type: PaymentEventType,
        payload: dict[str, Any],
        details: dict[str, Any] | None = None,
    ) -> Payment:
        """Write audit, outbox and replay rows for a payment that just changed."""
        append_audit(
            self.session,
            payment=payment,
            operation=self.scope,
            previous_status=previous_status,
            caller_service=self.context.caller_service,
            actor_id=self.context.actor_id,
            correlation_id=self.context.correlation_id,
            idempotency_key=self.key,
            details=details,
        )
        append_outbox_event(
            self.session,
            payment=payment,
            event_type=event_type,
            payload=payload,
            correlation_id=self.context.correlation_id,
            now=self.now,
        )
        return self.replay(payment)


def run_command(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    scope: str,
    key: str,
    request_hash: str,
    handler: Callable[[CommandScope], Payment],
) -> Payment:
    """Run one payment command in a single transaction guarded by its key.

    The advisory lock is taken before anything is read, so a concurrent duplicate
    either replays the stored response or blocks until the first one commits.
    """
    with session.begin():
        prepare_transaction(session, settings)
        now = database_now(session)
        replay = replay_or_lock(
            session, scope=scope, key=key, request_hash=request_hash, now=now
        )
        if replay is not None:
            return replay
        return handler(
            CommandScope(
                session=session,
                settings=settings,
                context=context,
                scope=scope,
                key=key,
                request_hash=request_hash,
                now=now,
            )
        )


def load_payment_for_update(
    session: Session, payment_id: str
) -> tuple[PaymentModel, Payment]:
    """Row-lock the payment and return both its row and its aggregate."""
    model = get_payment_model(session, payment_id, for_update=True)
    if model is None:
        raise PaymentNotFound(payment_id)
    return model, model_to_entity(model)


def payment_to_payload(payment: Payment) -> dict[str, Any]:
    return {
        "paymentId": payment.payment_id,
        "bookingId": payment.booking_id,
        "customerId": payment.customer_id,
        "amount": str(payment.amount),
        "currency": payment.currency,
        "paymentMethod": payment.payment_method,
        "provider": payment.provider,
        "methodFingerprint": payment.method_fingerprint,
        "providerScenario": payment.provider_scenario.value,
        "bookingEvidenceVersion": payment.booking_evidence_version,
        "bookingEvidenceId": payment.booking_evidence_id,
        "bookingEvidenceVerified": payment.booking_evidence_verified,
        "providerReference": payment.provider_reference,
        "status": payment.status.value,
        "lastStableStatus": (
            payment.last_stable_status.value if payment.last_stable_status else None
        ),
        "pendingOperation": (
            payment.pending_operation.value if payment.pending_operation else None
        ),
        "reconciliationStatus": payment.reconciliation_status.value,
        "reconciliationAttempts": payment.reconciliation_attempts,
        "reconciliationError": payment.reconciliation_error,
        "capturedAmount": str(payment.captured_amount),
        "refundedAmount": str(payment.refunded_amount),
        "failureCode": payment.failure_code,
        "failureReason": payment.failure_reason,
        "cancellationReason": payment.cancellation_reason,
        "resourceVersion": payment.resource_version,
        "createdAt": payment.created_at.isoformat(),
        "updatedAt": payment.updated_at.isoformat(),
        "authorizedAt": _datetime_text(payment.authorized_at),
        "capturedAt": _datetime_text(payment.captured_at),
        "cancelledAt": _datetime_text(payment.cancelled_at),
        "refundedAt": _datetime_text(payment.refunded_at),
        "unknownSince": _datetime_text(payment.unknown_since),
        "reconciliationDueAt": _datetime_text(payment.reconciliation_due_at),
        "lastReconciledAt": _datetime_text(payment.last_reconciled_at),
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
        method_fingerprint=_optional_text(payload.get("methodFingerprint")),
        provider_scenario=MockProviderScenario(
            str(payload.get("providerScenario", "MANUAL"))
        ),
        booking_evidence_version=(
            int(payload["bookingEvidenceVersion"])
            if payload.get("bookingEvidenceVersion") is not None
            else None
        ),
        booking_evidence_id=_optional_text(payload.get("bookingEvidenceId")),
        booking_evidence_verified=bool(
            payload.get("bookingEvidenceVerified", False)
        ),
        provider_reference=_optional_text(payload.get("providerReference")),
        status=PaymentStatus(str(payload["status"])),
        last_stable_status=(
            PaymentStatus(str(payload["lastStableStatus"]))
            if payload.get("lastStableStatus")
            else None
        ),
        pending_operation=(
            ProviderOperation(str(payload["pendingOperation"]))
            if payload.get("pendingOperation")
            else None
        ),
        reconciliation_status=ReconciliationStatus(
            str(payload.get("reconciliationStatus", "NOT_REQUIRED"))
        ),
        reconciliation_attempts=int(payload.get("reconciliationAttempts", 0)),
        reconciliation_error=_optional_text(payload.get("reconciliationError")),
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
        unknown_since=_optional_datetime(payload.get("unknownSince")),
        reconciliation_due_at=_optional_datetime(
            payload.get("reconciliationDueAt")
        ),
        last_reconciled_at=_optional_datetime(payload.get("lastReconciledAt")),
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
        "pendingOperation": (
            payment.pending_operation.value if payment.pending_operation else None
        ),
        "reconciliationStatus": payment.reconciliation_status.value,
        "resourceVersion": payment.resource_version,
        "occurredAt": payment.updated_at.isoformat(),
    }


def lock_refund_provider_reference(
    session: Session, payment: Payment, provider_reference: str
) -> RefundModel | None:
    """Serialize on a provider refund id and return the refund already using it.

    Without the advisory lock two concurrent refunds quoting the same provider
    reference could both pass the uniqueness check before either one inserts.
    """
    acquire_advisory_lock(
        session,
        advisory_lock_id(
            "RefundProviderReference", f"{payment.provider}:{provider_reference}"
        ),
    )
    return get_refund_by_provider_reference(
        session, payment.provider, provider_reference
    )


def refund_event_payload(payment: Payment, refund: Refund) -> dict[str, Any]:
    """Event body for a payment whose refunded amount just increased."""
    return {
        **event_payload(payment),
        "refundId": refund.refund_id,
        "refundAmount": str(refund.amount),
        "reason": refund.reason,
        "providerRefundReference": refund.provider_reference,
    }


def failure_event_payload(payment: Payment) -> dict[str, Any]:
    """Event body for a failed payment, including why it failed."""
    return {
        **event_payload(payment),
        "failureCode": payment.failure_code,
        "reason": payment.failure_reason,
    }


def ensure_same_failure_outcome(
    payment: Payment,
    *,
    failure_code: str | None,
    reason: str | None,
    provider_reference: str | None,
) -> None:
    """A retry under a new key may only restate the failure already stored.

    Reporting a different decline for a payment that already failed means the
    caller and the provider disagree, which must surface instead of overwriting.
    """
    if (
        payment.failure_code != failure_code
        or payment.failure_reason != reason
        or not payment.provider_reference_matches(provider_reference)
    ):
        raise InvalidRequest("Payment already records another failure outcome")


def event_type_for_status(status: PaymentStatus) -> PaymentEventType:
    mapping = {
        PaymentStatus.AUTHORIZED: PaymentEventType.AUTHORIZED,
        PaymentStatus.CAPTURED: PaymentEventType.SUCCEEDED,
        PaymentStatus.UNKNOWN: PaymentEventType.UNKNOWN,
        PaymentStatus.FAILED: PaymentEventType.FAILED,
        PaymentStatus.CANCELLED: PaymentEventType.CANCELLED,
        PaymentStatus.PARTIALLY_REFUNDED: PaymentEventType.REFUNDED,
        PaymentStatus.REFUNDED: PaymentEventType.REFUNDED,
    }
    return mapping[status]


def _datetime_text(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _optional_text(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_datetime(value: Any) -> datetime | None:
    return None if value is None else datetime.fromisoformat(str(value))
