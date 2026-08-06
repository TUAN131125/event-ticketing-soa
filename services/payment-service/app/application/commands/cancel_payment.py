"""Idempotent CancelPayment with unknown-outcome protection."""

from sqlalchemy.orm import Session

from app.application.common import (
    CommandScope,
    event_payload,
    load_payment_for_update,
    run_command,
    validate_context,
)
from app.application.provider_events import record_outcome_event, record_unknown_event
from app.application.provider_outcomes import apply_provider_outcome, is_noop
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
    validate_optional_identifier,
    validate_reason,
)
from app.domain.value_objects import ProviderOutcome, RequestContext
from app.infrastructure.database.repositories import apply_entity

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
    provider_status: PaymentStatus | None,
    expected_version: int,
) -> Payment:
    key = validate_context(context, idempotency_key)
    payment_id = validate_identifier(payment_id, "paymentId")
    reason = validate_reason(reason)
    provider_reference = validate_optional_identifier(
        provider_reference, "providerReference"
    )
    expected_version = validate_expected_version(expected_version)
    if provider_status not in {None, PaymentStatus.CANCELLED, PaymentStatus.UNKNOWN}:
        raise InvalidRequest("Cancel providerStatus must be CANCELLED or UNKNOWN")
    request_hash = canonical_request_hash(
        {
            "paymentId": payment_id,
            "reason": reason,
            "providerReference": provider_reference,
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
        handler=lambda command: _cancel(
            command,
            payment_id=payment_id,
            reason=reason,
            provider_reference=provider_reference,
            provider_status=provider_status,
            expected_version=expected_version,
        ),
    )


def _cancel(
    command: CommandScope,
    *,
    payment_id: str,
    reason: str,
    provider_reference: str | None,
    provider_status: PaymentStatus | None,
    expected_version: int,
) -> Payment:
    model, payment = load_payment_for_update(command.session, payment_id)
    if provider_status == PaymentStatus.UNKNOWN:
        previous = payment.status
        payment.mark_unknown(
            operation=ProviderOperation.CANCEL,
            reason=reason,
            provider_reference=provider_reference,
            expected_version=expected_version,
            now=command.now,
        )
        record_unknown_event(
            command.session,
            payment,
            operation=ProviderOperation.CANCEL,
            source=ProviderOutcomeSource.COMMAND,
            reason=reason,
            provider_reference=provider_reference,
            now=command.now,
        )
        apply_entity(model, payment)
        return command.record(
            payment,
            previous_status=previous,
            event_type=PaymentEventType.UNKNOWN,
            payload=event_payload(payment),
            details={"providerStatus": "UNKNOWN"},
        )

    outcome = ProviderOutcome(
        status=PaymentStatus.CANCELLED,
        operation=ProviderOperation.CANCEL,
        source=ProviderOutcomeSource.COMMAND,
        provider_reference=provider_reference,
        reason=reason,
        occurred_at=command.now,
    )
    if is_noop(payment, outcome):
        return command.replay(payment)
    previous = payment.status
    apply_provider_outcome(
        command.session,
        payment,
        outcome,
        expected_version=expected_version,
        now=command.now,
        reconciled=False,
    )
    record_outcome_event(command.session, payment, outcome, now=command.now)
    apply_entity(model, payment)
    return command.record(
        payment,
        previous_status=previous,
        event_type=PaymentEventType.CANCELLED,
        payload={**event_payload(payment), "reason": payment.cancellation_reason},
        details={"providerStatus": "CANCELLED"},
    )
