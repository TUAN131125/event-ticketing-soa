"""Immutable values used by the payment aggregate and provider adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from app.domain.enums import (
    MockProviderScenario,
    PaymentStatus,
    ProviderOperation,
    ProviderOutcomeSource,
    RefundKind,
)
from app.domain.exceptions import PaymentAmountMismatch
from app.domain.rules import (
    payment_token_fingerprint,
    mock_scenario_from_token,
    validate_currency,
    validate_identifier,
    validate_money,
    validate_payment_method,
)

if TYPE_CHECKING:
    from app.domain.entities import Payment


@dataclass(frozen=True, slots=True)
class BookingPaymentEvidence:
    """Authoritative total copied from Booking Service for integrity checking."""

    booking_id: str
    customer_id: str
    amount: Decimal
    currency: str
    resource_version: int | None = None
    evidence_id: str | None = None

    @classmethod
    def from_request(
        cls,
        *,
        booking_id: str,
        customer_id: str,
        amount: Decimal,
        currency: str,
        resource_version: int | None = None,
        evidence_id: str | None = None,
    ) -> BookingPaymentEvidence:
        if resource_version is not None and resource_version < 1:
            raise ValueError("booking evidence resourceVersion must be at least 1")
        return cls(
            booking_id=validate_identifier(booking_id, "bookingEvidence.bookingId"),
            customer_id=validate_identifier(
                customer_id, "bookingEvidence.customerId"
            ),
            amount=validate_money(amount, "bookingEvidence.amount"),
            currency=validate_currency(currency),
            resource_version=resource_version,
            evidence_id=(
                validate_identifier(evidence_id, "bookingEvidence.evidenceId")
                if evidence_id
                else None
            ),
        )

    def assert_matches(
        self,
        *,
        booking_id: str,
        customer_id: str,
        amount: Decimal,
        currency: str,
    ) -> None:
        actual_amount = validate_money(amount, "amount")
        actual_currency = validate_currency(currency)
        if self.booking_id != booking_id or self.customer_id != customer_id:
            raise PaymentAmountMismatch(
                expected_amount=str(self.amount),
                actual_amount=str(actual_amount),
                expected_currency=self.currency,
                actual_currency=actual_currency,
            )
        if self.amount != actual_amount or self.currency != actual_currency:
            raise PaymentAmountMismatch(
                expected_amount=str(self.amount),
                actual_amount=str(actual_amount),
                expected_currency=self.currency,
                actual_currency=actual_currency,
            )


@dataclass(frozen=True, slots=True)
class PaymentDraft:
    """Validated fields that define one payment intent."""

    booking_id: str
    customer_id: str
    amount: Decimal
    currency: str
    payment_method: str
    provider: str
    method_fingerprint: str | None = None
    provider_scenario: MockProviderScenario = MockProviderScenario.MANUAL
    booking_evidence_version: int | None = None
    booking_evidence_id: str | None = None
    booking_evidence_verified: bool = False

    @classmethod
    def from_request(
        cls,
        *,
        booking_id: str,
        customer_id: str,
        amount: Decimal,
        currency: str,
        payment_method: str,
        provider: str,
        method_token: str | None = None,
        booking_evidence: BookingPaymentEvidence | None = None,
    ) -> PaymentDraft:
        normalized_booking_id = validate_identifier(booking_id, "bookingId")
        normalized_customer_id = validate_identifier(customer_id, "customerId")
        normalized_amount = validate_money(amount, "amount")
        normalized_currency = validate_currency(currency)
        if booking_evidence is not None:
            booking_evidence.assert_matches(
                booking_id=normalized_booking_id,
                customer_id=normalized_customer_id,
                amount=normalized_amount,
                currency=normalized_currency,
            )
        return cls(
            booking_id=normalized_booking_id,
            customer_id=normalized_customer_id,
            amount=normalized_amount,
            currency=normalized_currency,
            payment_method=validate_payment_method(payment_method),
            provider=validate_identifier(provider, "provider", max_length=40),
            method_fingerprint=payment_token_fingerprint(method_token),
            provider_scenario=mock_scenario_from_token(method_token),
            booking_evidence_version=(
                booking_evidence.resource_version if booking_evidence else None
            ),
            booking_evidence_id=(
                booking_evidence.evidence_id if booking_evidence else None
            ),
            booking_evidence_verified=booking_evidence is not None,
        )

    def to_payload(self) -> dict[str, str | int | bool | None]:
        # Keep the exact legacy hash when callers use only legacy fields. New
        # integrity/provider fields are additive and enter the hash only when used.
        payload: dict[str, str | int | bool | None] = {
            "bookingId": self.booking_id,
            "customerId": self.customer_id,
            "amount": str(self.amount),
            "currency": self.currency,
            "paymentMethod": self.payment_method,
            "provider": self.provider,
        }
        if self.method_fingerprint is not None:
            payload["methodFingerprint"] = self.method_fingerprint
        if self.provider_scenario != MockProviderScenario.MANUAL:
            payload["providerScenario"] = self.provider_scenario.value
        if self.booking_evidence_verified:
            payload.update(
                {
                    "bookingEvidenceVersion": self.booking_evidence_version,
                    "bookingEvidenceId": self.booking_evidence_id,
                    "bookingEvidenceVerified": True,
                }
            )
        return payload



@dataclass(frozen=True, slots=True)
class ProviderOutcome:
    status: PaymentStatus
    operation: ProviderOperation
    source: ProviderOutcomeSource
    provider_reference: str | None = None
    provider_refund_reference: str | None = None
    refunded_amount: Decimal | None = None
    failure_code: str | None = None
    reason: str | None = None
    occurred_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class ProviderEvent:
    event_id: str
    payment_id: str
    provider: str
    operation: ProviderOperation
    status: PaymentStatus
    source: ProviderOutcomeSource
    payload_hash: str
    occurred_at: datetime
    received_at: datetime
    provider_reference: str | None = None
    provider_refund_reference: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    refunded_amount: Decimal | None = None
    failure_code: str | None = None
    reason: str | None = None

    def outcome(self) -> ProviderOutcome:
        return ProviderOutcome(
            status=self.status,
            operation=self.operation,
            source=self.source,
            provider_reference=self.provider_reference,
            provider_refund_reference=self.provider_refund_reference,
            refunded_amount=self.refunded_amount,
            failure_code=self.failure_code,
            reason=self.reason,
            occurred_at=self.occurred_at,
        )


@dataclass(frozen=True, slots=True)
class Refund:
    refund_id: str
    payment_id: str
    amount: Decimal
    currency: str
    reason: str
    kind: RefundKind
    provider_reference: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class RequestContext:
    correlation_id: str
    caller_service: str
    actor_id: str | None = None


@dataclass(frozen=True, slots=True)
class PaymentPage:
    items: tuple[Payment, ...]
    page: int
    page_size: int
    total: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total + self.page_size - 1) // self.page_size)
