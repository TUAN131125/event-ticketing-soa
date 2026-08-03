"""Atomic and idempotent CreatePayment command."""

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.application.common import (
    event_payload,
    payment_to_payload,
    prepare_transaction,
    replay_or_lock,
    save_replay,
    validate_context,
)
from app.config import Settings
from app.domain.entities import Payment
from app.domain.enums import PaymentEventType
from app.domain.exceptions import BookingPaymentConflict
from app.domain.rules import advisory_lock_id, canonical_request_hash
from app.domain.value_objects import RequestContext
from app.infrastructure.database.repositories import (
    acquire_advisory_lock,
    append_audit,
    append_outbox_event,
    database_now,
    entity_to_model,
    get_payment_by_booking,
    model_to_entity,
    next_payment_id,
)

SCOPE = "CreatePayment"


def create_payment(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    booking_id: str,
    customer_id: str,
    amount: Decimal,
    currency: str,
    payment_method: str,
    provider: str,
) -> Payment:
    key = validate_context(context, idempotency_key)
    candidate = Payment.create(
        payment_id="PAY-COMPARE",
        booking_id=booking_id,
        customer_id=customer_id,
        amount=amount,
        currency=currency,
        payment_method=payment_method,
        provider=provider,
        now=datetime.now(UTC),
    )
    booking_id = candidate.booking_id
    customer_id = candidate.customer_id
    amount = candidate.amount
    currency = candidate.currency
    payment_method = candidate.payment_method
    provider = candidate.provider
    request = _definition_payload(candidate)
    request_hash = canonical_request_hash(request)

    with session.begin():
        prepare_transaction(session, settings)
        now = database_now(session)
        replay = replay_or_lock(
            session,
            scope=SCOPE,
            key=key,
            request_hash=request_hash,
            now=now,
        )
        if replay is not None:
            return replay

        acquire_advisory_lock(session, advisory_lock_id("PaymentBooking", booking_id))
        existing_model = get_payment_by_booking(session, booking_id, for_update=True)
        if existing_model is not None:
            existing = model_to_entity(existing_model)
            if _definition_payload(existing) != request:
                raise BookingPaymentConflict(booking_id)
            save_replay(
                session,
                settings=settings,
                scope=SCOPE,
                key=key,
                request_hash=request_hash,
                payment=existing,
                now=now,
            )
            return existing

        payment = Payment.create(
            payment_id=next_payment_id(session),
            booking_id=booking_id,
            customer_id=customer_id,
            amount=amount,
            currency=currency,
            payment_method=payment_method,
            provider=provider,
            now=now,
        )
        session.add(entity_to_model(payment))
        append_audit(
            session,
            payment=payment,
            operation=SCOPE,
            previous_status=None,
            caller_service=context.caller_service,
            actor_id=context.actor_id,
            correlation_id=context.correlation_id,
            idempotency_key=key,
        )
        append_outbox_event(
            session,
            payment=payment,
            event_type=PaymentEventType.CREATED,
            payload=event_payload(payment),
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


def _definition_payload(payment: Payment) -> dict[str, object]:
    payload = payment_to_payload(payment)
    return {
        key: payload[key]
        for key in (
            "bookingId",
            "customerId",
            "amount",
            "currency",
            "paymentMethod",
            "provider",
        )
    }
