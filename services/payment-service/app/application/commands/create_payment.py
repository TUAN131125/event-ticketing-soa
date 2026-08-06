"""Atomic and idempotent CreatePayment command."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.application.common import (
    CommandScope,
    event_payload,
    run_command,
    validate_context,
)
from app.config import Settings
from app.domain.entities import Payment
from app.domain.enums import PaymentEventType
from app.domain.exceptions import BookingEvidenceRequired, BookingPaymentConflict
from app.domain.rules import advisory_lock_id, canonical_request_hash
from app.domain.value_objects import (
    BookingPaymentEvidence,
    PaymentDraft,
    RequestContext,
)
from app.infrastructure.database.repositories import (
    acquire_advisory_lock,
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
    method_token: str | None = None,
    booking_evidence: BookingPaymentEvidence | None = None,
) -> Payment:
    key = validate_context(context, idempotency_key)
    if settings.require_booking_evidence and booking_evidence is None:
        raise BookingEvidenceRequired()
    draft = PaymentDraft.from_request(
        booking_id=booking_id,
        customer_id=customer_id,
        amount=amount,
        currency=currency,
        payment_method=payment_method,
        provider=provider,
        method_token=method_token,
        booking_evidence=booking_evidence,
    )
    return run_command(
        session,
        settings,
        context,
        scope=SCOPE,
        key=key,
        request_hash=canonical_request_hash(draft.to_payload()),
        handler=lambda command: _create(command, draft),
    )


def _create(command: CommandScope, draft: PaymentDraft) -> Payment:
    session = command.session
    acquire_advisory_lock(session, advisory_lock_id("PaymentBooking", draft.booking_id))

    existing_model = get_payment_by_booking(session, draft.booking_id, for_update=True)
    if existing_model is not None:
        existing = model_to_entity(existing_model)
        if existing.definition() != draft:
            raise BookingPaymentConflict(draft.booking_id)
        return command.replay(existing)

    payment = Payment.create(
        payment_id=next_payment_id(session),
        draft=draft,
        now=command.now,
    )
    session.add(entity_to_model(payment))
    return command.record(
        payment,
        previous_status=None,
        event_type=PaymentEventType.CREATED,
        payload=event_payload(payment),
        details={
            "bookingEvidenceVerified": payment.booking_evidence_verified,
            "bookingEvidenceVersion": payment.booking_evidence_version,
            "providerScenario": payment.provider_scenario.value,
        },
    )
