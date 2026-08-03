"""Atomic full or partial RefundPayment command."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.application.common import (
    event_payload,
    prepare_transaction,
    replay_or_lock,
    save_replay,
    validate_context,
)
from app.config import Settings
from app.domain.entities import Payment
from app.domain.enums import PaymentEventType, RefundKind
from app.domain.exceptions import PaymentNotFound, ProviderReferenceConflict
from app.domain.rules import (
    advisory_lock_id,
    canonical_request_hash,
    validate_expected_version,
    validate_identifier,
    validate_money,
    validate_reason,
)
from app.domain.value_objects import RequestContext
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
    provider_refund_reference: str,
    expected_version: int,
) -> Payment:
    key = validate_context(context, idempotency_key)
    payment_id = validate_identifier(payment_id, "paymentId")
    amount = validate_money(amount, "refundAmount")
    reason = validate_reason(reason)
    provider_refund_reference = validate_identifier(
        provider_refund_reference, "providerRefundReference"
    )
    expected_version = validate_expected_version(expected_version)
    request_hash = canonical_request_hash(
        {
            "paymentId": payment_id,
            "amount": amount,
            "reason": reason,
            "providerRefundReference": provider_refund_reference,
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
        acquire_advisory_lock(
            session,
            advisory_lock_id(
                "RefundProviderReference",
                f"{payment.provider}:{provider_refund_reference}",
            ),
        )
        existing = get_refund_by_provider_reference(
            session, payment.provider, provider_refund_reference
        )
        if existing is not None:
            if (
                existing.payment_id != payment_id
                or Decimal(existing.amount) != amount
                or existing.reason != reason
            ):
                raise ProviderReferenceConflict()
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
        refund = payment.refund(
            refund_id=next_refund_id(session),
            amount=amount,
            reason=reason,
            provider_reference=provider_refund_reference,
            kind=RefundKind.REQUESTED,
            expected_version=expected_version,
            now=now,
        )
        apply_entity(model, payment)
        append_refund(session, payment=payment, refund=refund, idempotency_key=key)
        append_audit(
            session,
            payment=payment,
            operation=SCOPE,
            previous_status=previous,
            caller_service=context.caller_service,
            actor_id=context.actor_id,
            correlation_id=context.correlation_id,
            idempotency_key=key,
            details={"refundId": refund.refund_id, "amount": str(refund.amount)},
        )
        append_outbox_event(
            session,
            payment=payment,
            event_type=PaymentEventType.REFUNDED,
            payload={
                **event_payload(payment),
                "refundId": refund.refund_id,
                "refundAmount": str(refund.amount),
                "reason": refund.reason,
                "providerRefundReference": refund.provider_reference,
            },
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
