"""Verify and apply one immutable provider callback exactly once."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.application.common import (
    CommandScope,
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
    PaymentStatus,
    ProviderOperation,
    ProviderOutcomeSource,
)
from app.domain.exceptions import InvalidRequest, PaymentAmountMismatch
from app.domain.rules import canonical_request_hash, validate_identifier
from app.domain.value_objects import ProviderOutcome, RequestContext
from app.infrastructure.database.repositories import append_refund, apply_entity

SCOPE = "HandleProviderCallback"


def handle_provider_callback(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    event_id: str,
    payment_id: str,
    provider: str,
    operation: ProviderOperation,
    provider_status: PaymentStatus,
    provider_reference: str | None,
    provider_refund_reference: str | None,
    amount: Decimal | None,
    currency: str | None,
    observed_refunded_amount: Decimal | None,
    failure_code: str | None,
    reason: str | None,
    occurred_at: datetime,
    payload_hash: str,
) -> Payment:
    """Deduplicate by eventId and atomically persist ledger, state, audit and outbox."""
    event_id = validate_identifier(event_id, "eventId")
    payment_id = validate_identifier(payment_id, "paymentId")
    provider = validate_identifier(provider, "provider", max_length=40)
    key = validate_context(context, event_id)
    request_hash = canonical_request_hash(
        {
            "eventId": event_id,
            "paymentId": payment_id,
            "provider": provider,
            "operation": operation.value,
            "providerStatus": provider_status.value,
            "providerReference": provider_reference,
            "providerRefundReference": provider_refund_reference,
            "amount": amount,
            "currency": currency,
            "observedRefundedAmount": observed_refunded_amount,
            "failureCode": failure_code,
            "reason": reason,
            "occurredAt": occurred_at.isoformat(),
            "payloadHash": payload_hash,
        }
    )
    return run_command(
        session,
        settings,
        context,
        scope=SCOPE,
        key=key,
        request_hash=request_hash,
        handler=lambda command: _apply_callback(
            command,
            event_id=event_id,
            payment_id=payment_id,
            provider=provider,
            operation=operation,
            provider_status=provider_status,
            provider_reference=provider_reference,
            provider_refund_reference=provider_refund_reference,
            amount=amount,
            currency=currency,
            observed_refunded_amount=observed_refunded_amount,
            failure_code=failure_code,
            reason=reason,
            occurred_at=occurred_at,
            payload_hash=payload_hash,
        ),
    )


def _apply_callback(
    command: CommandScope,
    *,
    event_id: str,
    payment_id: str,
    provider: str,
    operation: ProviderOperation,
    provider_status: PaymentStatus,
    provider_reference: str | None,
    provider_refund_reference: str | None,
    amount: Decimal | None,
    currency: str | None,
    observed_refunded_amount: Decimal | None,
    failure_code: str | None,
    reason: str | None,
    occurred_at: datetime,
    payload_hash: str,
) -> Payment:
    model, payment = load_payment_for_update(command.session, payment_id)
    if payment.provider != provider:
        raise InvalidRequest("Provider callback does not belong to this payment")
    _assert_money_matches(payment, amount=amount, currency=currency)
    _assert_operation_matches_unknown(payment, operation)

    outcome = normalize_outcome(
        ProviderOutcome(
            status=provider_status,
            operation=operation,
            source=ProviderOutcomeSource.CALLBACK,
            provider_reference=provider_reference,
            provider_refund_reference=provider_refund_reference,
            refunded_amount=observed_refunded_amount,
            failure_code=failure_code,
            reason=reason,
            occurred_at=occurred_at,
        )
    )
    record_outcome_event(
        command.session,
        payment,
        outcome,
        now=command.now,
        event_id=event_id,
        amount=amount,
        currency=currency,
        payload_hash=payload_hash,
    )
    if is_noop(payment, outcome):
        return command.replay(payment)

    previous = payment.status
    reconciled = payment.status == PaymentStatus.UNKNOWN
    refund = apply_provider_outcome(
        command.session,
        payment,
        outcome,
        expected_version=payment.resource_version,
        now=command.now,
        reconciled=reconciled,
    )
    if refund is not None:
        append_refund(
            command.session,
            payment=payment,
            refund=refund,
            idempotency_key=event_id,
        )
    apply_entity(model, payment)
    details: dict[str, object] = {
        "eventId": event_id,
        "operation": operation.value,
        "providerStatus": provider_status.value,
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


def _assert_money_matches(
    payment: Payment,
    *,
    amount: Decimal | None,
    currency: str | None,
) -> None:
    if amount is None and currency is None:
        return
    if amount != payment.amount or (currency or "").upper() != payment.currency:
        raise PaymentAmountMismatch(
            expected_amount=str(payment.amount),
            actual_amount=str(amount),
            expected_currency=payment.currency,
            actual_currency=(currency or ""),
        )


def _assert_operation_matches_unknown(
    payment: Payment, operation: ProviderOperation
) -> None:
    if (
        payment.status == PaymentStatus.UNKNOWN
        and payment.pending_operation is not None
        and payment.pending_operation != operation
    ):
        raise InvalidRequest(
            "Provider callback operation does not match pending reconciliation"
        )
