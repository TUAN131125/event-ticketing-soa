"""Deterministic mock provider used by the project demo and fault tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.entities import Payment
from app.domain.enums import (
    MockProviderScenario,
    PaymentStatus,
    ProviderOperation,
    ProviderOutcomeSource,
)
from app.domain.exceptions import InvalidRequest
from app.domain.value_objects import ProviderOutcome


@dataclass(frozen=True, slots=True)
class ProviderCallResult:
    outcome: ProviderOutcome
    response_timed_out: bool = False


class MockProviderGateway:
    """Produces stable success/decline/timeout outcomes without card data."""

    def authorize(self, payment: Payment, now: datetime) -> ProviderCallResult:
        scenario = payment.provider_scenario
        reference = _reference(payment, ProviderOperation.AUTHORIZE)
        if scenario in {MockProviderScenario.SUCCESS, MockProviderScenario.TIMEOUT}:
            return ProviderCallResult(
                ProviderOutcome(
                    status=PaymentStatus.AUTHORIZED,
                    operation=ProviderOperation.AUTHORIZE,
                    source=ProviderOutcomeSource.MOCK_PROVIDER,
                    provider_reference=reference,
                    occurred_at=now,
                )
            )
        if scenario == MockProviderScenario.DECLINE:
            return ProviderCallResult(
                ProviderOutcome(
                    status=PaymentStatus.FAILED,
                    operation=ProviderOperation.AUTHORIZE,
                    source=ProviderOutcomeSource.MOCK_PROVIDER,
                    provider_reference=reference,
                    failure_code="PAYMENT_DECLINED",
                    reason="Mock provider declined the payment",
                    occurred_at=now,
                )
            )
        raise InvalidRequest(
            "Authorize outcome is required when payment has no mock scenario"
        )

    def capture(self, payment: Payment, now: datetime) -> ProviderCallResult:
        scenario = payment.provider_scenario
        reference = payment.provider_reference or _reference(
            payment, ProviderOperation.CAPTURE
        )
        if scenario == MockProviderScenario.SUCCESS:
            return ProviderCallResult(
                ProviderOutcome(
                    status=PaymentStatus.CAPTURED,
                    operation=ProviderOperation.CAPTURE,
                    source=ProviderOutcomeSource.MOCK_PROVIDER,
                    provider_reference=reference,
                    occurred_at=now,
                )
            )
        if scenario == MockProviderScenario.TIMEOUT:
            # The provider commits CAPTURED but the response is lost. The event is
            # persisted so a later ReconcilePayment can discover the final result.
            return ProviderCallResult(
                ProviderOutcome(
                    status=PaymentStatus.CAPTURED,
                    operation=ProviderOperation.CAPTURE,
                    source=ProviderOutcomeSource.MOCK_PROVIDER,
                    provider_reference=reference,
                    occurred_at=now,
                ),
                response_timed_out=True,
            )
        if scenario == MockProviderScenario.DECLINE:
            return ProviderCallResult(
                ProviderOutcome(
                    status=PaymentStatus.FAILED,
                    operation=ProviderOperation.CAPTURE,
                    source=ProviderOutcomeSource.MOCK_PROVIDER,
                    provider_reference=reference,
                    failure_code="PAYMENT_DECLINED",
                    reason="Mock provider declined capture",
                    occurred_at=now,
                )
            )
        raise InvalidRequest(
            "Capture outcome is required when payment has no mock scenario"
        )


def _reference(payment: Payment, operation: ProviderOperation) -> str:
    return f"mock-{operation.value.lower()}-{payment.payment_id.lower()}"
