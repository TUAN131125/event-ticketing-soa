"""Atomic and idempotent CancelPayment command."""

from sqlalchemy.orm import Session

from app.application.common import (
    ensure_payment_provider_reference_available,
    event_payload,
    prepare_transaction,
    replay_or_lock,
    save_replay,
    validate_context,
)
from app.config import Settings
from app.domain.entities import Payment
from app.domain.enums import PaymentEventType, PaymentStatus
from app.domain.exceptions import InvalidRequest, PaymentNotFound
from app.domain.rules import (
    canonical_request_hash,
    validate_expected_version,
    validate_identifier,
    validate_optional_identifier,
    validate_reason,
)
from app.domain.value_objects import RequestContext
from app.infrastructure.database.repositories import (
    append_audit,
    append_outbox_event,
    apply_entity,
    database_now,
    get_payment_model,
    model_to_entity,
)

SCOPE = "CancelPayment"


def cancel_payment(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    payment_id: str,
    reason: str,
    provider_reference: str | None,
    expected_version: int,
) -> Payment:
    key = validate_context(context, idempotency_key)
    payment_id = validate_identifier(payment_id, "paymentId")
    reason = validate_reason(reason)
    provider_reference = validate_optional_identifier(
        provider_reference, "providerReference"
    )
    expected_version = validate_expected_version(expected_version)
    request_hash = canonical_request_hash(
        {
            "paymentId": payment_id,
            "reason": reason,
            "providerReference": provider_reference,
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
        if payment.status == PaymentStatus.CANCELLED:
            if payment.cancellation_reason != reason or (
                provider_reference is not None
                and not payment.provider_reference_matches(provider_reference)
            ):
                raise InvalidRequest("Payment already records another cancellation")
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
        payment.cancel(
            reason=reason,
            provider_reference=provider_reference,
            expected_version=expected_version,
            now=now,
        )
        apply_entity(model, payment)
        append_audit(
            session,
            payment=payment,
            operation=SCOPE,
            previous_status=previous,
            caller_service=context.caller_service,
            actor_id=context.actor_id,
            correlation_id=context.correlation_id,
            idempotency_key=key,
            details={"reason": reason},
        )
        append_outbox_event(
            session,
            payment=payment,
            event_type=PaymentEventType.CANCELLED,
            payload={**event_payload(payment), "reason": reason},
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
