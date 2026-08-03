"""Reconcile authoritative provider state without allowing state regression."""

from datetime import datetime
from decimal import Decimal
from typing import cast

from sqlalchemy.orm import Session

from app.application.common import (
    ensure_payment_provider_reference_available,
    event_payload,
    event_type_for_status,
    prepare_transaction,
    replay_or_lock,
    save_replay,
    validate_context,
)
from app.config import Settings
from app.domain.entities import Payment
from app.domain.enums import PaymentStatus, RefundKind
from app.domain.exceptions import (
    InvalidRequest,
    PaymentNotFound,
    ProviderReferenceConflict,
)
from app.domain.rules import (
    advisory_lock_id,
    canonical_request_hash,
    validate_expected_version,
    validate_identifier,
    validate_money,
    validate_optional_identifier,
    validate_reason,
)
from app.domain.value_objects import Refund, RequestContext
from app.infrastructure.database.repositories import (
    acquire_advisory_lock,
    append_audit,
    append_outbox_event,
    append_refund,
    apply_entity,
    database_now,
    get_payment_model,
    get_refund_by_provider_reference,
    model_to_entity,
    next_refund_id,
)

SCOPE = "ReconcilePayment"
REFUND_STATES = {PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED}
CAPTURED_OR_LATER = {
    PaymentStatus.CAPTURED,
    PaymentStatus.PARTIALLY_REFUNDED,
    PaymentStatus.REFUNDED,
}
AUTHORIZED_OR_LATER = {PaymentStatus.AUTHORIZED, *CAPTURED_OR_LATER}


def reconcile_payment(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    payment_id: str,
    provider_status: PaymentStatus,
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
    provider_reference = validate_optional_identifier(
        provider_reference, "providerReference"
    )
    provider_refund_reference = validate_optional_identifier(
        provider_refund_reference, "providerRefundReference"
    )
    if provider_status == PaymentStatus.PENDING:
        raise InvalidRequest("PENDING is not a reconcilable provider outcome")
    if observed_refunded_amount is not None:
        observed_refunded_amount = validate_money(
            observed_refunded_amount, "observedRefundedAmount", allow_zero=True
        )
    if failure_code is not None:
        failure_code = validate_identifier(failure_code, "failureCode")
    if reason is not None:
        reason = validate_reason(reason)
    _validate_outcome_fields(
        provider_status=provider_status,
        provider_reference=provider_reference,
        provider_refund_reference=provider_refund_reference,
        observed_refunded_amount=observed_refunded_amount,
        failure_code=failure_code,
        reason=reason,
    )
    request_hash = canonical_request_hash(
        {
            "paymentId": payment_id,
            "providerStatus": provider_status.value,
            "providerReference": provider_reference,
            "providerRefundReference": provider_refund_reference,
            "observedRefundedAmount": observed_refunded_amount,
            "failureCode": failure_code,
            "reason": reason,
            "expectedVersion": expected_version,
        }
    )
    with session.begin():
        prepare_transaction(session, settings)
        now = database_now(session)
        replay = replay_or_lock(
            session, scope=SCOPE, key=key, request_hash=request_hash, now=now
        )
        if replay is not None:
            return replay
        model = get_payment_model(session, payment_id, for_update=True)
        if model is None:
            raise PaymentNotFound(payment_id)
        payment = model_to_entity(model)
        ensure_payment_provider_reference_available(
            session, payment, provider_reference
        )
        if provider_status in REFUND_STATES:
            if (
                provider_reference is not None
                and not payment.provider_reference_matches(provider_reference)
            ):
                raise InvalidRequest("Provider reference does not match local payment")
            refund_reference = cast(str, provider_refund_reference)
            acquire_advisory_lock(
                session,
                advisory_lock_id(
                    "RefundProviderReference",
                    f"{payment.provider}:{refund_reference}",
                ),
            )
            existing_refund = get_refund_by_provider_reference(
                session, payment.provider, refund_reference
            )
            if existing_refund is not None:
                if existing_refund.payment_id != payment.payment_id:
                    raise ProviderReferenceConflict()
                if observed_refunded_amount != payment.refunded_amount:
                    raise ProviderReferenceConflict()
        if _is_noop(
            payment,
            provider_status=provider_status,
            provider_reference=provider_reference,
            observed_refunded_amount=observed_refunded_amount,
            failure_code=failure_code,
            reason=reason,
        ):
            save_replay(
                session,
                settings=settings,
                scope=SCOPE,
                key=key,
                request_hash=request_hash,
                payment=payment,
                now=now,
            )
            return payment
        previous = payment.status
        refund = _apply_provider_outcome(
            session,
            payment,
            provider_status=provider_status,
            provider_reference=provider_reference,
            provider_refund_reference=provider_refund_reference,
            observed_refunded_amount=observed_refunded_amount,
            failure_code=failure_code,
            reason=reason,
            expected_version=expected_version,
            now=now,
        )
        apply_entity(model, payment)
        if refund is not None:
            append_refund(session, payment=payment, refund=refund, idempotency_key=key)
        details: dict[str, object] = {"providerStatus": provider_status.value}
        if refund is not None:
            details.update({"refundId": refund.refund_id, "amount": str(refund.amount)})
        append_audit(
            session,
            payment=payment,
            operation=SCOPE,
            previous_status=previous,
            caller_service=context.caller_service,
            actor_id=context.actor_id,
            correlation_id=context.correlation_id,
            idempotency_key=key,
            details=details,
        )
        payload = event_payload(payment)
        if payment.status == PaymentStatus.FAILED:
            payload.update(
                {"failureCode": payment.failure_code, "reason": payment.failure_reason}
            )
        elif payment.status == PaymentStatus.CANCELLED:
            payload["reason"] = payment.cancellation_reason
        elif refund is not None:
            payload.update(
                {
                    "refundId": refund.refund_id,
                    "refundAmount": str(refund.amount),
                    "reason": refund.reason,
                    "providerRefundReference": refund.provider_reference,
                }
            )
        append_outbox_event(
            session,
            payment=payment,
            event_type=event_type_for_status(payment.status),
            payload=payload,
            correlation_id=context.correlation_id,
            now=now,
        )
        save_replay(
            session,
            settings=settings,
            scope=SCOPE,
            key=key,
            request_hash=request_hash,
            payment=payment,
            now=now,
        )
        return payment


def _validate_outcome_fields(
    *,
    provider_status: PaymentStatus,
    provider_reference: str | None,
    provider_refund_reference: str | None,
    observed_refunded_amount: Decimal | None,
    failure_code: str | None,
    reason: str | None,
) -> None:
    if provider_status in {PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED}:
        if provider_reference is None:
            raise InvalidRequest("providerReference is required for this outcome")
        if any(
            value is not None
            for value in (
                provider_refund_reference,
                observed_refunded_amount,
                failure_code,
                reason,
            )
        ):
            raise InvalidRequest("This provider outcome contains unrelated fields")
    elif provider_status == PaymentStatus.FAILED:
        if failure_code is None or reason is None:
            raise InvalidRequest("failureCode and reason are required for FAILED")
        if (
            provider_refund_reference is not None
            or observed_refunded_amount is not None
        ):
            raise InvalidRequest("FAILED cannot include refund fields")
    elif provider_status == PaymentStatus.CANCELLED:
        if reason is None:
            raise InvalidRequest("reason is required for CANCELLED")
        if (
            failure_code is not None
            or provider_refund_reference is not None
            or observed_refunded_amount is not None
        ):
            raise InvalidRequest("CANCELLED contains unrelated outcome fields")
    elif provider_status in REFUND_STATES:
        if provider_refund_reference is None or observed_refunded_amount is None:
            raise InvalidRequest(
                "providerRefundReference and observedRefundedAmount are required "
                "for a refund outcome"
            )
        if failure_code is not None:
            raise InvalidRequest("A refund outcome cannot include failureCode")


def _is_noop(
    payment: Payment,
    *,
    provider_status: PaymentStatus,
    provider_reference: str | None,
    observed_refunded_amount: Decimal | None,
    failure_code: str | None,
    reason: str | None,
) -> bool:
    if (
        provider_status == PaymentStatus.AUTHORIZED
        and payment.status in AUTHORIZED_OR_LATER
    ):
        if not payment.provider_reference_matches(provider_reference):
            raise InvalidRequest("Provider reference does not match local payment")
        return True
    if (
        provider_status == PaymentStatus.CAPTURED
        and payment.status in CAPTURED_OR_LATER
    ):
        if not payment.provider_reference_matches(provider_reference):
            raise InvalidRequest("Provider reference does not match local payment")
        return True
    if payment.status != provider_status:
        return False
    if provider_status in {PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED}:
        if not payment.provider_reference_matches(provider_reference):
            raise InvalidRequest("Provider reference does not match local payment")
    elif provider_status == PaymentStatus.FAILED:
        if (
            payment.failure_code != failure_code
            or payment.failure_reason != reason
            or (
                provider_reference is not None
                and not payment.provider_reference_matches(provider_reference)
            )
        ):
            raise InvalidRequest("Payment already records another failure outcome")
    elif provider_status == PaymentStatus.CANCELLED:
        if payment.cancellation_reason != reason or (
            provider_reference is not None
            and not payment.provider_reference_matches(provider_reference)
        ):
            raise InvalidRequest("Payment already records another cancellation")
    if provider_status in REFUND_STATES:
        if observed_refunded_amount != payment.refunded_amount:
            return False
    return True


def _apply_provider_outcome(
    session: Session,
    payment: Payment,
    *,
    provider_status: PaymentStatus,
    provider_reference: str | None,
    provider_refund_reference: str | None,
    observed_refunded_amount: Decimal | None,
    failure_code: str | None,
    reason: str | None,
    expected_version: int,
    now: datetime,
) -> Refund | None:
    if provider_status == PaymentStatus.AUTHORIZED:
        payment.authorize(
            provider_reference=cast(str, provider_reference),
            expected_version=expected_version,
            now=now,
        )
        return None
    if provider_status == PaymentStatus.CAPTURED:
        payment.capture(
            provider_reference=cast(str, provider_reference),
            expected_version=expected_version,
            now=now,
            allow_direct=True,
        )
        return None
    if provider_status == PaymentStatus.FAILED:
        payment.fail(
            failure_code=cast(str, failure_code),
            reason=cast(str, reason),
            provider_reference=provider_reference,
            expected_version=expected_version,
            now=now,
        )
        return None
    if provider_status == PaymentStatus.CANCELLED:
        payment.cancel(
            reason=cast(str, reason),
            provider_reference=provider_reference,
            expected_version=expected_version,
            now=now,
        )
        return None
    if provider_status in REFUND_STATES:
        refunded_amount = cast(Decimal, observed_refunded_amount)
        refund_reference = cast(str, provider_refund_reference)
        if refunded_amount < payment.refunded_amount:
            raise InvalidRequest("Provider refund state is older than local state")
        delta = refunded_amount - payment.refunded_amount
        if delta == 0:
            raise InvalidRequest("Reconciliation does not change local refund state")
        refund = payment.refund(
            refund_id=next_refund_id(session),
            amount=delta,
            reason=reason or "provider reconciliation",
            provider_reference=refund_reference,
            kind=RefundKind.RECONCILIATION,
            expected_version=expected_version,
            now=now,
        )
        if payment.status != provider_status:
            raise InvalidRequest("providerStatus does not match observedRefundedAmount")
        return refund
    raise InvalidRequest("Unsupported providerStatus")
