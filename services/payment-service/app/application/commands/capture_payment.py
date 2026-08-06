"""CapturePayment with unknown-outcome protection and mock-provider support."""

from datetime import datetime

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
from app.infrastructure.providers.mock import MockProviderGateway, ProviderCallResult

SCOPE = "CapturePayment"


def capture_payment(
    session: Session,
    settings: Settings,
    context: RequestContext,
    *,
    idempotency_key: str,
    payment_id: str,
    succeeded: bool | None,
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
    _validate_request(succeeded, provider_status)
    request_hash = canonical_request_hash(
        {
            "paymentId": payment_id,
            "succeeded": succeeded,
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
        handler=lambda command: _capture(
            command,
            payment_id=payment_id,
            succeeded=succeeded,
            provider_status=provider_status,
            provider_reference=provider_reference,
            failure_code=failure_code,
            reason=reason,
            expected_version=expected_version,
        ),
    )


def _validate_request(
    succeeded: bool | None,
    provider_status: PaymentStatus | None,
) -> None:
    if succeeded is not None and provider_status is not None:
        raise InvalidRequest("Use succeeded or providerStatus, not both")
    if provider_status not in {
        None,
        PaymentStatus.CAPTURED,
        PaymentStatus.FAILED,
        PaymentStatus.UNKNOWN,
    }:
        raise InvalidRequest(
            "Capture providerStatus must be CAPTURED, FAILED or UNKNOWN"
        )


def _capture(
    command: CommandScope,
    *,
    payment_id: str,
    succeeded: bool | None,
    provider_status: PaymentStatus | None,
    provider_reference: str | None,
    failure_code: str | None,
    reason: str | None,
    expected_version: int,
) -> Payment:
    model, payment = load_payment_for_update(command.session, payment_id)
    if provider_status == PaymentStatus.UNKNOWN:
        return _mark_unknown(
            command,
            model,
            payment,
            expected_version=expected_version,
            provider_reference=provider_reference,
            reason=reason or "Provider capture response timed out",
        )

    result = _outcome(
        payment,
        succeeded=succeeded,
        provider_status=provider_status,
        provider_reference=provider_reference,
        failure_code=failure_code,
        reason=reason,
        now=command.now,
    )
    if result.response_timed_out:
        # Persist the provider's committed result, but do not apply it locally.
        # ReconcilePayment reads this immutable event and resolves UNKNOWN.
        record_outcome_event(
            command.session,
            payment,
            result.outcome,
            now=command.now,
        )
        return _mark_unknown(
            command,
            model,
            payment,
            expected_version=expected_version,
            provider_reference=result.outcome.provider_reference,
            reason="Provider capture committed but response timed out",
        )

    outcome = result.outcome
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


def _mark_unknown(
    command: CommandScope,
    model,
    payment: Payment,
    *,
    expected_version: int,
    provider_reference: str | None,
    reason: str,
) -> Payment:
    previous = payment.status
    payment.mark_unknown(
        operation=ProviderOperation.CAPTURE,
        reason=reason,
        provider_reference=provider_reference,
        expected_version=expected_version,
        now=command.now,
    )
    record_unknown_event(
        command.session,
        payment,
        operation=ProviderOperation.CAPTURE,
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


def _outcome(
    payment: Payment,
    *,
    succeeded: bool | None,
    provider_status: PaymentStatus | None,
    provider_reference: str | None,
    failure_code: str | None,
    reason: str | None,
    now: datetime,
) -> ProviderCallResult:
    if succeeded is None and provider_status is None:
        return MockProviderGateway().capture(payment, now)
    status = provider_status or (
        PaymentStatus.CAPTURED if succeeded else PaymentStatus.FAILED
    )
    if status == PaymentStatus.CAPTURED:
        if provider_reference is None:
            raise InvalidRequest("providerReference is required for capture")
        if failure_code is not None or reason is not None:
            raise InvalidRequest("Capture success cannot include failure fields")
    else:
        failure_code = failure_code or "PAYMENT_DECLINED"
        reason = reason or "Provider declined capture"
    return ProviderCallResult(
        ProviderOutcome(
            status=status,
            operation=ProviderOperation.CAPTURE,
            source=ProviderOutcomeSource.COMMAND,
            provider_reference=provider_reference,
            failure_code=failure_code,
            reason=reason,
            occurred_at=now,
        )
    )
