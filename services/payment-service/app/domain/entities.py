"""Persistence-independent payment aggregate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.enums import PaymentStatus, RefundKind
from app.domain.exceptions import (
    InvalidRequest,
    ProviderReferenceConflict,
    VersionConflict,
)
from app.domain.rules import (
    ensure_transition_allowed,
    validate_currency,
    validate_identifier,
    validate_money,
    validate_optional_identifier,
    validate_payment_method,
    validate_reason,
)
from app.domain.value_objects import Refund


@dataclass(slots=True)
class Payment:
    payment_id: str
    booking_id: str
    customer_id: str
    amount: Decimal
    currency: str
    payment_method: str
    provider: str
    status: PaymentStatus
    captured_amount: Decimal
    refunded_amount: Decimal
    resource_version: int
    created_at: datetime
    updated_at: datetime
    provider_reference: str | None = None
    failure_code: str | None = None
    failure_reason: str | None = None
    cancellation_reason: str | None = None
    authorized_at: datetime | None = None
    captured_at: datetime | None = None
    cancelled_at: datetime | None = None
    refunded_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        payment_id: str,
        booking_id: str,
        customer_id: str,
        amount: Decimal,
        currency: str,
        payment_method: str,
        provider: str,
        now: datetime,
    ) -> Payment:
        return cls(
            payment_id=validate_identifier(payment_id, "paymentId"),
            booking_id=validate_identifier(booking_id, "bookingId"),
            customer_id=validate_identifier(customer_id, "customerId"),
            amount=validate_money(amount, "amount"),
            currency=validate_currency(currency),
            payment_method=validate_payment_method(payment_method),
            provider=validate_identifier(provider, "provider", max_length=40),
            status=PaymentStatus.PENDING,
            captured_amount=Decimal("0.00"),
            refunded_amount=Decimal("0.00"),
            resource_version=1,
            created_at=now,
            updated_at=now,
        )

    def check_version(self, expected_version: int) -> None:
        if self.resource_version != expected_version:
            raise VersionConflict(expected_version, self.resource_version)

    def authorize(
        self,
        *,
        provider_reference: str,
        expected_version: int,
        now: datetime,
    ) -> None:
        self.check_version(expected_version)
        ensure_transition_allowed(self.status, PaymentStatus.AUTHORIZED)
        self._set_provider_reference(provider_reference)
        self.status = PaymentStatus.AUTHORIZED
        self.authorized_at = now
        self._advance(now)

    def capture(
        self,
        *,
        provider_reference: str,
        expected_version: int,
        now: datetime,
        allow_direct: bool = False,
    ) -> None:
        self.check_version(expected_version)
        if self.status == PaymentStatus.PENDING and not allow_direct:
            raise InvalidRequest("Payment must be authorized before capture")
        ensure_transition_allowed(self.status, PaymentStatus.CAPTURED)
        self._set_provider_reference(provider_reference)
        self.status = PaymentStatus.CAPTURED
        self.captured_amount = self.amount
        self.captured_at = now
        self._advance(now)

    def fail(
        self,
        *,
        failure_code: str,
        reason: str,
        provider_reference: str | None,
        expected_version: int,
        now: datetime,
    ) -> None:
        self.check_version(expected_version)
        ensure_transition_allowed(self.status, PaymentStatus.FAILED)
        if provider_reference is not None:
            self._set_provider_reference(provider_reference)
        self.failure_code = validate_identifier(failure_code, "failureCode")
        self.failure_reason = validate_reason(reason)
        self.status = PaymentStatus.FAILED
        self._advance(now)

    def cancel(
        self,
        *,
        reason: str,
        provider_reference: str | None,
        expected_version: int,
        now: datetime,
    ) -> None:
        self.check_version(expected_version)
        ensure_transition_allowed(self.status, PaymentStatus.CANCELLED)
        if provider_reference is not None:
            self._set_provider_reference(provider_reference)
        self.cancellation_reason = validate_reason(reason)
        self.status = PaymentStatus.CANCELLED
        self.cancelled_at = now
        self._advance(now)

    def refund(
        self,
        *,
        refund_id: str,
        amount: Decimal,
        reason: str,
        provider_reference: str,
        kind: RefundKind,
        expected_version: int,
        now: datetime,
    ) -> Refund:
        self.check_version(expected_version)
        if self.status not in {
            PaymentStatus.CAPTURED,
            PaymentStatus.PARTIALLY_REFUNDED,
        }:
            target = PaymentStatus.REFUNDED
            ensure_transition_allowed(self.status, target)
        refund_amount = validate_money(amount, "refundAmount")
        remaining = self.captured_amount - self.refunded_amount
        if refund_amount > remaining:
            raise InvalidRequest(
                "refundAmount cannot exceed the unrefunded captured amount",
                details={
                    "refundAmount": str(refund_amount),
                    "availableAmount": str(remaining),
                },
            )
        target = (
            PaymentStatus.REFUNDED
            if refund_amount == remaining
            else PaymentStatus.PARTIALLY_REFUNDED
        )
        ensure_transition_allowed(self.status, target)
        normalized_reference = validate_identifier(
            provider_reference, "providerRefundReference"
        )
        normalized_reason = validate_reason(reason)
        self.refunded_amount += refund_amount
        self.status = target
        if target == PaymentStatus.REFUNDED:
            self.refunded_at = now
        self._advance(now)
        return Refund(
            refund_id=validate_identifier(refund_id, "refundId"),
            payment_id=self.payment_id,
            amount=refund_amount,
            currency=self.currency,
            reason=normalized_reason,
            kind=kind,
            provider_reference=normalized_reference,
            created_at=now,
        )

    def _set_provider_reference(self, value: str) -> None:
        normalized = validate_identifier(value, "providerReference")
        if (
            self.provider_reference is not None
            and self.provider_reference != normalized
        ):
            raise ProviderReferenceConflict()
        self.provider_reference = normalized

    def provider_reference_matches(self, value: str | None) -> bool:
        normalized = validate_optional_identifier(value, "providerReference")
        return self.provider_reference == normalized

    def _advance(self, now: datetime) -> None:
        self.resource_version += 1
        self.updated_at = now
