from decimal import Decimal

import pytest

from app.application.provider_outcomes import normalize_outcome
from app.domain.enums import (
    PaymentStatus,
    ProviderOperation,
    ProviderOutcomeSource,
)
from app.domain.exceptions import InvalidRequest
from app.domain.value_objects import ProviderOutcome


def outcome(operation: ProviderOperation, status: PaymentStatus) -> ProviderOutcome:
    return ProviderOutcome(
        operation=operation,
        status=status,
        source=ProviderOutcomeSource.CALLBACK,
        provider_reference="provider-1",
        provider_refund_reference=(
            "refund-1" if operation == ProviderOperation.REFUND else None
        ),
        refunded_amount=(
            Decimal("10.00") if operation == ProviderOperation.REFUND else None
        ),
        failure_code="PAYMENT_DECLINED" if status == PaymentStatus.FAILED else None,
        reason="declined" if status == PaymentStatus.FAILED else None,
    )


def test_provider_operation_must_match_final_status() -> None:
    normalize_outcome(outcome(ProviderOperation.AUTHORIZE, PaymentStatus.AUTHORIZED))
    normalize_outcome(outcome(ProviderOperation.CAPTURE, PaymentStatus.CAPTURED))
    normalize_outcome(
        outcome(ProviderOperation.REFUND, PaymentStatus.PARTIALLY_REFUNDED)
    )
    with pytest.raises(InvalidRequest, match="AUTHORIZE cannot produce CAPTURED"):
        normalize_outcome(outcome(ProviderOperation.AUTHORIZE, PaymentStatus.CAPTURED))
    with pytest.raises(InvalidRequest, match="CANCEL cannot produce FAILED"):
        normalize_outcome(outcome(ProviderOperation.CANCEL, PaymentStatus.FAILED))
