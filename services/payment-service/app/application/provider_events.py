"""Immutable provider-event ledger helpers."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.domain.entities import Payment
from app.domain.enums import PaymentStatus, ProviderOperation, ProviderOutcomeSource
from app.domain.rules import canonical_request_hash
from app.domain.value_objects import ProviderEvent, ProviderOutcome
from app.infrastructure.database.repositories import append_provider_event


def record_outcome_event(
    session: Session,
    payment: Payment,
    outcome: ProviderOutcome,
    *,
    now: datetime,
    event_id: str | None = None,
    amount: Decimal | None = None,
    currency: str | None = None,
    payload_hash: str | None = None,
) -> ProviderEvent:
    payload = {
        "paymentId": payment.payment_id,
        "provider": payment.provider,
        "operation": outcome.operation.value,
        "providerStatus": outcome.status.value,
        "providerReference": outcome.provider_reference,
        "providerRefundReference": outcome.provider_refund_reference,
        "observedRefundedAmount": outcome.refunded_amount,
        "failureCode": outcome.failure_code,
        "reason": outcome.reason,
        "occurredAt": (outcome.occurred_at or now).isoformat(),
        "amount": amount,
        "currency": currency,
    }
    event = ProviderEvent(
        event_id=event_id or str(uuid.uuid4()),
        payment_id=payment.payment_id,
        provider=payment.provider,
        operation=outcome.operation,
        status=outcome.status,
        source=outcome.source,
        payload_hash=payload_hash or canonical_request_hash(payload),
        occurred_at=outcome.occurred_at or now,
        received_at=now,
        provider_reference=outcome.provider_reference,
        provider_refund_reference=outcome.provider_refund_reference,
        amount=amount,
        currency=currency,
        refunded_amount=outcome.refunded_amount,
        failure_code=outcome.failure_code,
        reason=outcome.reason,
    )
    append_provider_event(session, event)
    return event


def record_unknown_event(
    session: Session,
    payment: Payment,
    *,
    operation: ProviderOperation,
    source: ProviderOutcomeSource,
    reason: str,
    provider_reference: str | None,
    now: datetime,
) -> ProviderEvent:
    return record_outcome_event(
        session,
        payment,
        ProviderOutcome(
            status=PaymentStatus.UNKNOWN,
            operation=operation,
            source=source,
            provider_reference=provider_reference,
            reason=reason,
            occurred_at=now,
        ),
        now=now,
    )
