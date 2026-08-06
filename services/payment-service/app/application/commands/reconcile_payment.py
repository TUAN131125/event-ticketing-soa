"""Resolve UNKNOWN payment outcomes from provider evidence without regression."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.application.common import (
    CommandScope,
    event_payload,
    event_type_for_status,
    load_payment_for_update,
    run_command,
    validate_context,
)
from app.application.provider_events import record_outcome_event
from app.application.provider_outcomes import (
    apply_provider_outcome,
    is_noop,
    normalize_outcome,
    outcome_event_payload,
)
from app.config import Settings
from app.domain.entities import Payment
from app.domain.enums import (
    PaymentEventType,
    PaymentStatus,
    ProviderOperation,
    ProviderOutcomeSource,
)
from app.domain.exceptions import InvalidRequest
from app.domain.rules import (
    canonical_request_hash,
    validate_expected_version,
    validate_identifier,
)
from app.domain.value_objects import ProviderOutcome, RequestContext
from app.infrastructure.database.repositories import (
    append_refund,
    apply_entity,
    latest_final_provider_event,
)

SCOPE = "ReconcilePayment"


@dataclass(frozen=True, slots=True)
class OutcomeResolution:
    outcome: ProviderOutcome | None
    already_recorded: bool = False
    unavailable_reason: str | None = None
    record_failure: bool = False


def reconcile_payment(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    payment_id: str,
    provider_status: PaymentStatus | None,
    provider_reference: str | None,
    provider_refund_reference: str | None,
    observed_refunded_amount: Decimal | None,
    failure_code: str | None,
    reason: str | None,
    expected_version: int,
) -> Payment:
    key = validate_context(context, idempotency_key)
    payment_id = validate_identifier(payment_id, "paymentId")
    expected_version = validate_expected_version(expected_version)
    request_hash = canonical_request_hash(
        {
            "paymentId": payment_id,
            "providerStatus": provider_status.value if provider_status else None,
            "providerReference": provider_reference,
            "providerRefundReference": provider_refund_reference,
            "observedRefundedAmount": observed_refunded_amount,
            "failureCode": failure_code,
            "reason": reason,
            "expectedVersion": expected_version,
        }
    )
    return run_command(
        session,
        settings,
        context,
        scope=SCOPE,
        key=key,
        request_hash=request_hash,
        handler=lambda command: _reconcile(
            command,
            payment_id=payment_id,
            provider_status=provider_status,
            provider_reference=provider_reference,
            provider_refund_reference=provider_refund_reference,
            observed_refunded_amount=observed_refunded_amount,
            failure_code=failure_code,
            reason=reason,
            expected_version=expected_version,
        ),
    )


def _reconcile(
    command: CommandScope,
    *,
    payment_id: str,
    provider_status: PaymentStatus | None,
    provider_reference: str | None,
    provider_refund_reference: str | None,
    observed_refunded_amount: Decimal | None,
    failure_code: str | None,
    reason: str | None,
    expected_version: int,
) -> Payment:
    model, payment = load_payment_for_update(command.session, payment_id)
    resolution = _resolve_outcome(
        command,
        payment,
        provider_status=provider_status,
        provider_reference=provider_reference,
        provider_refund_reference=provider_refund_reference,
        observed_refunded_amount=observed_refunded_amount,
        failure_code=failure_code,
        reason=reason,
    )
    if resolution.outcome is None:
        return _record_unavailable(
            command,
            model,
            payment,
            expected_version=expected_version,
            resolution=resolution,
        )

    outcome = normalize_outcome(resolution.outcome)
    if is_noop(payment, outcome):
        return command.replay(payment)

    previous = payment.status
    reconciled = payment.status == PaymentStatus.UNKNOWN
    refund = apply_provider_outcome(
        command.session,
        payment,
        outcome,
        expected_version=expected_version,
        now=command.now,
        reconciled=reconciled,
    )
    if refund is not None:
        append_refund(
            command.session,
            payment=payment,
            refund=refund,
            idempotency_key=command.key,
        )
    if not resolution.already_recorded:
        record_outcome_event(command.session, payment, outcome, now=command.now)
    apply_entity(model, payment)
    details: dict[str, object] = {
        "providerStatus": outcome.status.value,
        "source": outcome.source.value,
        "reconciledFromUnknown": reconciled,
    }
    if refund is not None:
        details.update({"refundId": refund.refund_id, "amount": str(refund.amount)})
    return command.record(
        payment,
        previous_status=previous,
        event_type=event_type_for_status(payment.status),
        payload=outcome_event_payload(payment, refund),
        details=details,
    )


def _record_unavailable(
    command: CommandScope,
    model,
    payment: Payment,
    *,
    expected_version: int,
    resolution: OutcomeResolution,
) -> Payment:
    if not resolution.record_failure:
        return command.replay(payment)

    next_attempt = payment.reconciliation_attempts + 1
    exhausted = (
        next_attempt >= command.settings.provider_reconciliation_max_attempts
    )
    delay_seconds = reconciliation_delay_seconds(
        attempts=payment.reconciliation_attempts,
        initial=command.settings.provider_reconciliation_initial_delay_seconds,
        maximum=command.settings.provider_reconciliation_max_delay_seconds,
    )
    previous = payment.status
    next_due_at = (
        None
        if exhausted
        else command.now + timedelta(seconds=delay_seconds)
    )
    payment.record_reconciliation_failure(
        reason=resolution.unavailable_reason or "Provider outcome is unavailable",
        expected_version=expected_version,
        now=command.now,
        next_due_at=next_due_at,
    )
    apply_entity(model, payment)
    return command.record(
        payment,
        previous_status=previous,
        event_type=PaymentEventType.UNKNOWN,
        payload=event_payload(payment),
        details={
            "providerUnavailable": True,
            "reconciliationAttempt": payment.reconciliation_attempts,
            "reconciliationExhausted": exhausted,
            "nextRetryAt": (
                next_due_at.isoformat() if next_due_at is not None else None
            ),
        },
    )


def _resolve_outcome(
    command: CommandScope,
    payment: Payment,
    *,
    provider_status: PaymentStatus | None,
    provider_reference: str | None,
    provider_refund_reference: str | None,
    observed_refunded_amount: Decimal | None,
    failure_code: str | None,
    reason: str | None,
) -> OutcomeResolution:
    if provider_status is not None:
        if provider_status in {PaymentStatus.PENDING, PaymentStatus.UNKNOWN}:
            raise InvalidRequest("providerStatus must be a final outcome")
        return OutcomeResolution(
            ProviderOutcome(
                status=provider_status,
                operation=_operation_for(payment, provider_status),
                source=ProviderOutcomeSource.RECONCILIATION,
                provider_reference=provider_reference,
                provider_refund_reference=provider_refund_reference,
                refunded_amount=observed_refunded_amount,
                failure_code=failure_code,
                reason=reason,
                occurred_at=command.now,
            )
        )

    if payment.status != PaymentStatus.UNKNOWN:
        raise InvalidRequest(
            "providerStatus can be omitted only for an UNKNOWN payment"
        )
    if payment.reconciliation_attempts >= (
        command.settings.provider_reconciliation_max_attempts
    ):
        return OutcomeResolution(
            None,
            unavailable_reason="Reconciliation attempts are exhausted",
            record_failure=False,
        )
    if (
        payment.reconciliation_due_at is not None
        and payment.reconciliation_due_at > command.now
    ):
        return OutcomeResolution(
            None,
            unavailable_reason="Reconciliation backoff is active",
            record_failure=False,
        )

    event = latest_final_provider_event(
        command.session,
        payment.payment_id,
        payment.pending_operation,
    )
    if event is None:
        return OutcomeResolution(
            None,
            unavailable_reason="Provider final outcome is not available",
            record_failure=True,
        )
    return OutcomeResolution(event.outcome(), already_recorded=True)


def reconciliation_delay_seconds(*, attempts: int, initial: int, maximum: int) -> int:
    """Bounded exponential backoff used by manual and worker reconciliation."""
    if attempts < 0 or initial < 1 or maximum < 1:
        raise ValueError("reconciliation delay arguments are invalid")
    return min(initial * (2**attempts), maximum)


def _operation_for(
    payment: Payment,
    provider_status: PaymentStatus,
) -> ProviderOperation:
    if payment.pending_operation is not None:
        return payment.pending_operation
    if provider_status == PaymentStatus.AUTHORIZED:
        return ProviderOperation.AUTHORIZE
    if provider_status == PaymentStatus.CAPTURED:
        return ProviderOperation.CAPTURE
    if provider_status == PaymentStatus.CANCELLED:
        return ProviderOperation.CANCEL
    if provider_status in {
        PaymentStatus.PARTIALLY_REFUNDED,
        PaymentStatus.REFUNDED,
    }:
        return ProviderOperation.REFUND
    return ProviderOperation.CAPTURE


# Compatibility helpers retained for existing unit/consumer tests.
def _validate_outcome_fields(
    *,
    provider_status: PaymentStatus,
    provider_reference: str | None,
    provider_refund_reference: str | None,
    observed_refunded_amount: Decimal | None,
    failure_code: str | None,
    reason: str | None,
) -> None:
    from app.application.provider_outcomes import validate_outcome_fields

    validate_outcome_fields(
        ProviderOutcome(
            status=provider_status,
            operation=ProviderOperation.CAPTURE,
            source=ProviderOutcomeSource.RECONCILIATION,
            provider_reference=provider_reference,
            provider_refund_reference=provider_refund_reference,
            refunded_amount=observed_refunded_amount,
            failure_code=failure_code,
            reason=reason,
        )
    )


def _is_noop(
    payment: Payment,
    *,
    provider_status: PaymentStatus,
    provider_reference: str | None,
    observed_refunded_amount: Decimal | None,
    failure_code: str | None,
    reason: str | None,
) -> bool:
    return is_noop(
        payment,
        ProviderOutcome(
            status=provider_status,
            operation=_operation_for(payment, provider_status),
            source=ProviderOutcomeSource.RECONCILIATION,
            provider_reference=provider_reference,
            refunded_amount=observed_refunded_amount,
            failure_code=failure_code,
            reason=reason,
        ),
    )
