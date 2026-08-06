"""Idempotent bounded RefundPayment command."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.application.common import (
    CommandScope,
    load_payment_for_update,
    refund_event_payload,
    run_command,
    validate_context,
)
from app.application.provider_events import record_outcome_event, record_unknown_event
from app.config import Settings
from app.domain.entities import Payment
from app.domain.enums import (
    PaymentEventType,
    PaymentStatus,
    ProviderOperation,
    ProviderOutcomeSource,
    RefundKind,
)
from app.domain.exceptions import InvalidRequest, ProviderReferenceConflict
from app.domain.rules import (
    canonical_request_hash,
    validate_expected_version,
    validate_identifier,
    validate_money,
    validate_optional_identifier,
    validate_reason,
)
from app.domain.value_objects import ProviderOutcome, RequestContext
from app.infrastructure.database.repositories import (
    append_refund,
    apply_entity,
    get_refund_by_provider_reference,
    next_refund_id,
)
from app.application.common import lock_refund_provider_reference

SCOPE = "RefundPayment"


def refund_payment(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    payment_id: str,
    amount: Decimal,
    reason: str,
    provider_refund_reference: str | None,
    provider_status: PaymentStatus | None,
    expected_version: int,
) -> Payment:
    key = validate_context(context, idempotency_key)
    payment_id = validate_identifier(payment_id, "paymentId")
    amount = validate_money(amount, "refundAmount")
    reason = validate_reason(reason)
    provider_refund_reference = validate_optional_identifier(
        provider_refund_reference, "providerRefundReference"
    )
    expected_version = validate_expected_version(expected_version)
    if provider_status not in {
        None,
        PaymentStatus.PARTIALLY_REFUNDED,
        PaymentStatus.REFUNDED,
        PaymentStatus.UNKNOWN,
    }:
        raise InvalidRequest(
            "Refund providerStatus must be PARTIALLY_REFUNDED, REFUNDED or UNKNOWN"
        )
    if provider_status != PaymentStatus.UNKNOWN and provider_refund_reference is None:
        raise InvalidRequest("providerRefundReference is required for refund success")
    request_hash = canonical_request_hash(
        {
            "paymentId": payment_id,
            "amount": amount,
            "reason": reason,
            "providerRefundReference": provider_refund_reference,
            "providerStatus": provider_status.value if provider_status else None,
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
        handler=lambda command: _refund(
            command,
            payment_id=payment_id,
            amount=amount,
            reason=reason,
            provider_refund_reference=provider_refund_reference,
            provider_status=provider_status,
            expected_version=expected_version,
        ),
    )


def _refund(
    command: CommandScope,
    *,
    payment_id: str,
    amount: Decimal,
    reason: str,
    provider_refund_reference: str | None,
    provider_status: PaymentStatus | None,
    expected_version: int,
) -> Payment:
    model, payment = load_payment_for_update(command.session, payment_id)
    if provider_status == PaymentStatus.UNKNOWN:
        previous = payment.status
        payment.mark_unknown(
            operation=ProviderOperation.REFUND,
            reason=reason,
            provider_reference=payment.provider_reference,
            expected_version=expected_version,
            now=command.now,
        )
        record_unknown_event(
            command.session,
            payment,
            operation=ProviderOperation.REFUND,
            source=ProviderOutcomeSource.COMMAND,
            reason=reason,
            provider_reference=payment.provider_reference,
            now=command.now,
        )
        apply_entity(model, payment)
        return command.record(
            payment,
            previous_status=previous,
            event_type=PaymentEventType.UNKNOWN,
            payload={
                "paymentId": payment.payment_id,
                "bookingId": payment.booking_id,
                "status": payment.status.value,
                "pendingOperation": ProviderOperation.REFUND.value,
                "resourceVersion": payment.resource_version,
            },
            details={"providerStatus": "UNKNOWN", "amount": str(amount)},
        )

    reference = str(provider_refund_reference)
    existing = lock_refund_provider_reference(command.session, payment, reference)
    if existing is not None:
        if existing.payment_id != payment.payment_id:
            raise ProviderReferenceConflict()
        if Decimal(existing.amount) != amount or existing.reason != reason:
            raise ProviderReferenceConflict()
        return command.replay(payment)

    previous = payment.status
    refund = payment.refund(
        refund_id=next_refund_id(command.session),
        amount=amount,
        reason=reason,
        provider_reference=reference,
        kind=RefundKind.REQUESTED,
        expected_version=expected_version,
        now=command.now,
    )
    if provider_status is not None and payment.status != provider_status:
        raise InvalidRequest("providerStatus does not match refund amount")
    append_refund(
        command.session,
        payment=payment,
        refund=refund,
        idempotency_key=command.key,
    )
    outcome = ProviderOutcome(
        status=payment.status,
        operation=ProviderOperation.REFUND,
        source=ProviderOutcomeSource.COMMAND,
        provider_reference=payment.provider_reference,
        provider_refund_reference=reference,
        refunded_amount=payment.refunded_amount,
        reason=reason,
        occurred_at=command.now,
    )
    record_outcome_event(command.session, payment, outcome, now=command.now)
    apply_entity(model, payment)
    return command.record(
        payment,
        previous_status=previous,
        event_type=PaymentEventType.REFUNDED,
        payload=refund_event_payload(payment, refund),
        details={"refundId": refund.refund_id, "amount": str(refund.amount)},
    )
