"""Record a verified provider authorization outcome."""

from datetime import datetime
from typing import cast

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

SCOPE = "AuthorizePayment"
ADVANCED_SUCCESS_STATES = {
    PaymentStatus.AUTHORIZED,
    PaymentStatus.CAPTURED,
    PaymentStatus.PARTIALLY_REFUNDED,
    PaymentStatus.REFUNDED,
}


def authorize_payment(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    payment_id: str,
    approved: bool,
    provider_reference: str | None,
    failure_code: str | None,
    reason: str | None,
    expected_version: int,
) -> Payment:
    key = validate_context(context, idempotency_key)
    payment_id = validate_identifier(payment_id, "paymentId")
    provider_reference = validate_optional_identifier(
        provider_reference, "providerReference"
    )
    expected_version = validate_expected_version(expected_version)
    if approved:
        if provider_reference is None:
            raise InvalidRequest("providerReference is required when approved is true")
        if failure_code is not None or reason is not None:
            raise InvalidRequest("Failure details are not allowed for an approval")
    else:
        if failure_code is None or reason is None:
            raise InvalidRequest("failureCode and reason are required when declined")
        failure_code = validate_identifier(failure_code, "failureCode")
        reason = validate_reason(reason)
    request_hash = canonical_request_hash(
        {
            "paymentId": payment_id,
            "approved": approved,
            "providerReference": provider_reference,
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
        if approved and payment.status in ADVANCED_SUCCESS_STATES:
            if not payment.provider_reference_matches(provider_reference):
                raise InvalidRequest("Authorization uses another provider reference")
            return _save_terminal_replay(
                session, settings, key, request_hash, payment, now
            )
        if not approved and payment.status == PaymentStatus.FAILED:
            if (
                payment.failure_code != failure_code
                or payment.failure_reason != reason
                or not payment.provider_reference_matches(provider_reference)
            ):
                raise InvalidRequest("Payment already records another failure outcome")
            return _save_terminal_replay(
                session, settings, key, request_hash, payment, now
            )
        previous = payment.status
        if approved:
            payment.authorize(
                provider_reference=cast(str, provider_reference),
                expected_version=expected_version,
                now=now,
            )
            event_type = PaymentEventType.AUTHORIZED
            payload = event_payload(payment)
        else:
            payment.fail(
                failure_code=cast(str, failure_code),
                reason=cast(str, reason),
                provider_reference=provider_reference,
                expected_version=expected_version,
                now=now,
            )
            event_type = PaymentEventType.FAILED
            payload = {
                **event_payload(payment),
                "failureCode": payment.failure_code,
                "reason": payment.failure_reason,
            }
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
            details={"approved": approved},
        )
        append_outbox_event(
            session,
            payment=payment,
            event_type=event_type,
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


def _save_terminal_replay(
    session: Session,
    settings: Settings,
    key: str,
    request_hash: str,
    payment: Payment,
    now: datetime,
) -> Payment:
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
