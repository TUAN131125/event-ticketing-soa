"""AuthorizePayment with legacy outcome support and mock-provider execution."""

from sqlalchemy.orm import Session

from app.application.common import (
    CommandScope,
    event_payload,
    event_type_for_status,
    failure_event_payload,
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
from app.infrastructure.providers.mock import MockProviderGateway

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
    approved: bool | None,
    provider_status: PaymentStatus | None,
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
    if failure_code is not None:
        failure_code = validate_identifier(failure_code, "failureCode")
    if reason is not None:
        reason = validate_reason(reason)
    _validate_request(approved, provider_status)
    request_hash = canonical_request_hash(
        {
            "paymentId": payment_id,
            "approved": approved,
            "providerStatus": provider_status.value if provider_status else None,
            "providerReference": provider_reference,
            "failureCode": failure_code,
            "reason": reason,
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
        handler=lambda command: _authorize(
            command,
            payment_id=payment_id,
            approved=approved,
            provider_status=provider_status,
            provider_reference=provider_reference,
            failure_code=failure_code,
            reason=reason,
            expected_version=expected_version,
        ),
    )


def _validate_request(
    approved: bool | None,
    provider_status: PaymentStatus | None,
) -> None:
    if approved is not None and provider_status is not None:
        raise InvalidRequest("Use approved or providerStatus, not both")
    allowed_statuses = {
        None,
        PaymentStatus.AUTHORIZED,
        PaymentStatus.FAILED,
        PaymentStatus.UNKNOWN,
    }
    if provider_status not in allowed_statuses:
        raise InvalidRequest(
            "Authorize providerStatus must be AUTHORIZED, FAILED or UNKNOWN"
        )


def _authorize(
    command: CommandScope,
    *,
    payment_id: str,
    approved: bool | None,
    provider_status: PaymentStatus | None,
    provider_reference: str | None,
    failure_code: str | None,
    reason: str | None,
    expected_version: int,
) -> Payment:
    model, payment = load_payment_for_update(command.session, payment_id)
    if provider_status == PaymentStatus.UNKNOWN:
        unknown_reason = reason or "Provider authorization response timed out"
        previous = payment.status
        payment.mark_unknown(
            operation=ProviderOperation.AUTHORIZE,
            reason=unknown_reason,
            provider_reference=provider_reference,
            expected_version=expected_version,
            now=command.now,
        )
        record_unknown_event(
            command.session,
            payment,
            operation=ProviderOperation.AUTHORIZE,
            source=ProviderOutcomeSource.COMMAND,
            reason=unknown_reason,
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

    result = _outcome(
        payment,
        approved=approved,
        provider_status=provider_status,
        provider_reference=provider_reference,
        failure_code=failure_code,
        reason=reason,
        now=command.now,
    )
    outcome = result
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
    payload = (
        failure_event_payload(payment)
        if payment.status == PaymentStatus.FAILED
        else event_payload(payment)
    )
    return command.record(
        payment,
        previous_status=previous,
        event_type=event_type_for_status(payment.status),
        payload=payload,
        details={
            "providerStatus": outcome.status.value,
            "source": outcome.source.value,
        },
    )


def _outcome(
    payment: Payment,
    *,
    approved: bool | None,
    provider_status: PaymentStatus | None,
    provider_reference: str | None,
    failure_code: str | None,
    reason: str | None,
    now,
) -> ProviderOutcome:
    if approved is None and provider_status is None:
        return MockProviderGateway().authorize(payment, now).outcome
    status = provider_status or (
        PaymentStatus.AUTHORIZED if approved else PaymentStatus.FAILED
    )
    if status == PaymentStatus.AUTHORIZED:
        if provider_reference is None:
            raise InvalidRequest("providerReference is required for authorization")
        if failure_code is not None or reason is not None:
            raise InvalidRequest("Authorization cannot include failure fields")
    else:
        failure_code = failure_code or "PAYMENT_DECLINED"
        reason = reason or "Provider declined the payment"
    return ProviderOutcome(
        status=status,
        operation=ProviderOperation.AUTHORIZE,
        source=ProviderOutcomeSource.COMMAND,
        provider_reference=provider_reference,
        failure_code=failure_code,
        reason=reason,
        occurred_at=now,
    )
