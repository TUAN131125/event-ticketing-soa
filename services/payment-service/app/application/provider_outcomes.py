"""Shared validation and application of authoritative provider outcomes."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import cast

from sqlalchemy.orm import Session

from app.application.common import (
    ensure_payment_provider_reference_available,
    failure_event_payload,
    lock_refund_provider_reference,
    refund_event_payload,
)
from app.domain.entities import Payment
from app.domain.enums import PaymentStatus, ProviderOperation, RefundKind
from app.domain.exceptions import InvalidRequest, ProviderReferenceConflict
from app.domain.rules import (
    validate_identifier,
    validate_money,
    validate_optional_identifier,
    validate_reason,
)
from app.domain.value_objects import ProviderOutcome, Refund
from app.infrastructure.database.repositories import next_refund_id

REFUND_STATES = {PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED}
CAPTURED_OR_LATER = {
    PaymentStatus.CAPTURED,
    PaymentStatus.PARTIALLY_REFUNDED,
    PaymentStatus.REFUNDED,
}
AUTHORIZED_OR_LATER = {PaymentStatus.AUTHORIZED, *CAPTURED_OR_LATER}
FINAL_PROVIDER_STATUSES = {
    PaymentStatus.AUTHORIZED,
    PaymentStatus.CAPTURED,
    PaymentStatus.FAILED,
    PaymentStatus.CANCELLED,
    PaymentStatus.PARTIALLY_REFUNDED,
    PaymentStatus.REFUNDED,
}
OPERATION_OUTCOMES: dict[ProviderOperation, frozenset[PaymentStatus]] = {
    ProviderOperation.AUTHORIZE: frozenset(
        {PaymentStatus.AUTHORIZED, PaymentStatus.FAILED}
    ),
    ProviderOperation.CAPTURE: frozenset(
        {PaymentStatus.CAPTURED, PaymentStatus.FAILED}
    ),
    ProviderOperation.CANCEL: frozenset({PaymentStatus.CANCELLED}),
    ProviderOperation.REFUND: frozenset(REFUND_STATES),
}


def normalize_outcome(outcome: ProviderOutcome) -> ProviderOutcome:
    status = outcome.status
    if status not in FINAL_PROVIDER_STATUSES:
        raise InvalidRequest("providerStatus is not a final provider outcome")
    provider_reference = validate_optional_identifier(
        outcome.provider_reference, "providerReference"
    )
    refund_reference = validate_optional_identifier(
        outcome.provider_refund_reference, "providerRefundReference"
    )
    refunded_amount = outcome.refunded_amount
    if refunded_amount is not None:
        refunded_amount = validate_money(
            refunded_amount, "observedRefundedAmount", allow_zero=True
        )
    failure_code = (
        validate_identifier(outcome.failure_code, "failureCode")
        if outcome.failure_code
        else None
    )
    reason = validate_reason(outcome.reason) if outcome.reason else None
    if status not in OPERATION_OUTCOMES[outcome.operation]:
        raise InvalidRequest(
            f"{outcome.operation.value} cannot produce {status.value}"
        )
    normalized = ProviderOutcome(
        status=status,
        operation=outcome.operation,
        source=outcome.source,
        provider_reference=provider_reference,
        provider_refund_reference=refund_reference,
        refunded_amount=refunded_amount,
        failure_code=failure_code,
        reason=reason,
        occurred_at=outcome.occurred_at,
    )
    validate_outcome_fields(normalized)
    return normalized


def validate_outcome_fields(outcome: ProviderOutcome) -> None:
    status = outcome.status
    if status in {PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED}:
        if outcome.provider_reference is None:
            raise InvalidRequest("providerReference is required for this outcome")
        if any(
            value is not None
            for value in (
                outcome.provider_refund_reference,
                outcome.refunded_amount,
                outcome.failure_code,
                outcome.reason,
            )
        ):
            raise InvalidRequest("Provider outcome contains unrelated fields")
    elif status == PaymentStatus.FAILED:
        if outcome.failure_code is None or outcome.reason is None:
            raise InvalidRequest("failureCode and reason are required for FAILED")
        if (
            outcome.provider_refund_reference is not None
            or outcome.refunded_amount is not None
        ):
            raise InvalidRequest("FAILED cannot include refund fields")
    elif status == PaymentStatus.CANCELLED:
        if outcome.reason is None:
            raise InvalidRequest("reason is required for CANCELLED")
        if any(
            value is not None
            for value in (
                outcome.failure_code,
                outcome.provider_refund_reference,
                outcome.refunded_amount,
            )
        ):
            raise InvalidRequest("CANCELLED contains unrelated outcome fields")
    elif status in REFUND_STATES:
        if outcome.provider_refund_reference is None or outcome.refunded_amount is None:
            raise InvalidRequest(
                "providerRefundReference and observedRefundedAmount are required "
                "for a refund outcome"
            )
        if outcome.failure_code is not None:
            raise InvalidRequest("A refund outcome cannot include failureCode")


def is_noop(payment: Payment, outcome: ProviderOutcome) -> bool:
    status = outcome.status
    if status == PaymentStatus.AUTHORIZED and payment.status in AUTHORIZED_OR_LATER:
        _ensure_reference(payment, outcome.provider_reference)
        return True
    if status == PaymentStatus.CAPTURED and payment.status in CAPTURED_OR_LATER:
        _ensure_reference(payment, outcome.provider_reference)
        return True
    if payment.status != status:
        return False
    if status in {PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED}:
        _ensure_reference(payment, outcome.provider_reference)
    elif status == PaymentStatus.FAILED:
        if (
            payment.failure_code != outcome.failure_code
            or payment.failure_reason != outcome.reason
            or (
                outcome.provider_reference is not None
                and not payment.provider_reference_matches(outcome.provider_reference)
            )
        ):
            raise InvalidRequest("Payment already records another failure outcome")
    elif status == PaymentStatus.CANCELLED:
        if payment.cancellation_reason != outcome.reason or (
            outcome.provider_reference is not None
            and not payment.provider_reference_matches(outcome.provider_reference)
        ):
            raise InvalidRequest("Payment already records another cancellation")
    elif status in REFUND_STATES:
        return outcome.refunded_amount == payment.refunded_amount
    return True


def apply_provider_outcome(
    session: Session,
    payment: Payment,
    outcome: ProviderOutcome,
    *,
    expected_version: int,
    now: datetime,
    reconciled: bool,
) -> Refund | None:
    outcome = normalize_outcome(outcome)
    ensure_payment_provider_reference_available(
        session, payment, outcome.provider_reference
    )
    if outcome.status in REFUND_STATES:
        guard_refund_outcome(session, payment, outcome)
    if is_noop(payment, outcome):
        return None

    if outcome.status == PaymentStatus.AUTHORIZED:
        payment.authorize(
            provider_reference=cast(str, outcome.provider_reference),
            expected_version=expected_version,
            now=now,
            reconciled=reconciled,
        )
        return None
    if outcome.status == PaymentStatus.CAPTURED:
        payment.capture(
            provider_reference=cast(str, outcome.provider_reference),
            expected_version=expected_version,
            now=now,
            allow_direct=True,
            reconciled=reconciled,
        )
        return None
    if outcome.status == PaymentStatus.FAILED:
        payment.fail(
            failure_code=cast(str, outcome.failure_code),
            reason=cast(str, outcome.reason),
            provider_reference=outcome.provider_reference,
            expected_version=expected_version,
            now=now,
            operation=outcome.operation,
            reconciled=reconciled,
        )
        return None
    if outcome.status == PaymentStatus.CANCELLED:
        payment.cancel(
            reason=cast(str, outcome.reason),
            provider_reference=outcome.provider_reference,
            expected_version=expected_version,
            now=now,
            reconciled=reconciled,
        )
        return None
    if outcome.status in REFUND_STATES:
        return apply_refund_outcome(
            session,
            payment,
            outcome,
            expected_version=expected_version,
            now=now,
            reconciled=reconciled,
        )
    raise InvalidRequest("Unsupported providerStatus")


def guard_refund_outcome(
    session: Session,
    payment: Payment,
    outcome: ProviderOutcome,
) -> None:
    if outcome.provider_reference is not None:
        _ensure_reference(payment, outcome.provider_reference)
    reference = cast(str, outcome.provider_refund_reference)
    existing_refund = lock_refund_provider_reference(session, payment, reference)
    if existing_refund is None:
        return
    if existing_refund.payment_id != payment.payment_id:
        raise ProviderReferenceConflict()
    if outcome.refunded_amount != payment.refunded_amount:
        raise ProviderReferenceConflict()


def apply_refund_outcome(
    session: Session,
    payment: Payment,
    outcome: ProviderOutcome,
    *,
    expected_version: int,
    now: datetime,
    reconciled: bool,
) -> Refund:
    observed = cast(Decimal, outcome.refunded_amount)
    if observed < payment.refunded_amount:
        raise InvalidRequest("Provider refund state is older than local state")
    delta = observed - payment.refunded_amount
    if delta == 0:
        raise InvalidRequest("Provider refund outcome does not change local state")
    refund = payment.refund(
        refund_id=next_refund_id(session),
        amount=delta,
        reason=outcome.reason or "provider reconciliation",
        provider_reference=cast(str, outcome.provider_refund_reference),
        kind=RefundKind.RECONCILIATION,
        expected_version=expected_version,
        now=now,
        reconciled=reconciled,
    )
    if payment.status != outcome.status:
        raise InvalidRequest("providerStatus does not match observedRefundedAmount")
    return refund


def outcome_event_payload(payment: Payment, refund: Refund | None) -> dict[str, object]:
    from app.application.common import event_payload

    if payment.status == PaymentStatus.FAILED:
        return failure_event_payload(payment)
    if payment.status == PaymentStatus.CANCELLED:
        return {**event_payload(payment), "reason": payment.cancellation_reason}
    if refund is not None:
        return refund_event_payload(payment, refund)
    return event_payload(payment)


def _ensure_reference(payment: Payment, provider_reference: str | None) -> None:
    if not payment.provider_reference_matches(provider_reference):
        raise InvalidRequest("Provider reference does not match local payment")
