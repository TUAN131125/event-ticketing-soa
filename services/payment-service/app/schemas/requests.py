"""Closed and backwards-compatible request contracts for Payment commands."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.enums import PaymentStatus, ProviderOperation
from app.domain.rules import amount_from_minor


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class BookingPaymentEvidenceRequest(ClosedModel):
    booking_id: str = Field(alias="bookingId", min_length=1, max_length=128)
    customer_id: str = Field(alias="customerId", min_length=1, max_length=128)
    amount: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=2
    )
    amount_minor: int | None = Field(default=None, alias="amountMinor", gt=0)
    currency: str = Field(min_length=3, max_length=3)
    resource_version: int | None = Field(
        default=None, alias="resourceVersion", ge=1
    )
    evidence_id: str | None = Field(
        default=None, alias="evidenceId", min_length=1, max_length=128
    )

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def resolve_money(self) -> BookingPaymentEvidenceRequest:
        if self.amount is None and self.amount_minor is None:
            raise ValueError("bookingEvidence requires amount or amountMinor")
        from_minor = (
            amount_from_minor(self.amount_minor, self.currency)
            if self.amount_minor is not None
            else None
        )
        if (
            self.amount is not None
            and from_minor is not None
            and self.amount != from_minor
        ):
            raise ValueError("bookingEvidence amount and amountMinor do not match")
        self.amount = self.amount or from_minor
        return self

    def resolved_amount(self) -> Decimal:
        assert self.amount is not None
        return self.amount


class CreatePaymentRequest(ClosedModel):
    booking_id: str = Field(alias="bookingId", min_length=1, max_length=128)
    customer_id: str = Field(alias="customerId", min_length=1, max_length=128)
    amount: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=2
    )
    amount_minor: int | None = Field(default=None, alias="amountMinor", gt=0)
    currency: str = Field(min_length=3, max_length=3)
    payment_method: str | None = Field(
        default=None, alias="paymentMethod", min_length=1, max_length=40
    )
    method_token: str | None = Field(
        default=None, alias="methodToken", min_length=8, max_length=256
    )
    provider: str = Field(default="mock-provider", min_length=1, max_length=40)
    booking_evidence: BookingPaymentEvidenceRequest | None = Field(
        default=None, alias="bookingEvidence"
    )

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def resolve_compatible_fields(self) -> CreatePaymentRequest:
        if self.amount is None and self.amount_minor is None:
            raise ValueError("amount or amountMinor is required")
        from_minor = (
            amount_from_minor(self.amount_minor, self.currency)
            if self.amount_minor is not None
            else None
        )
        if (
            self.amount is not None
            and from_minor is not None
            and self.amount != from_minor
        ):
            raise ValueError("amount and amountMinor do not match")
        self.amount = self.amount or from_minor
        if self.payment_method is None and self.method_token is None:
            raise ValueError("paymentMethod or methodToken is required")
        if self.payment_method is None:
            self.payment_method = "MOCK_TOKEN"
        return self

    def resolved_amount(self) -> Decimal:
        assert self.amount is not None
        return self.amount

    def resolved_payment_method(self) -> str:
        assert self.payment_method is not None
        return self.payment_method


class AuthorizePaymentRequest(ClosedModel):
    # Legacy callers send approved. New callers may send providerStatus=UNKNOWN
    # or omit both to invoke the deterministic mock provider.
    approved: bool | None = None
    provider_status: PaymentStatus | None = Field(
        default=None, alias="providerStatus"
    )
    provider_reference: str | None = Field(
        default=None, alias="providerReference", min_length=1, max_length=128
    )
    failure_code: str | None = Field(
        default=None, alias="failureCode", min_length=1, max_length=128
    )
    reason: str | None = Field(default=None, min_length=1, max_length=2_000)
    expected_version: int | None = Field(
        default=None, alias="expectedVersion", ge=1
    )


class CapturePaymentRequest(ClosedModel):
    succeeded: bool | None = None
    provider_status: PaymentStatus | None = Field(
        default=None, alias="providerStatus"
    )
    provider_reference: str | None = Field(
        default=None, alias="providerReference", min_length=1, max_length=128
    )
    failure_code: str | None = Field(
        default=None, alias="failureCode", min_length=1, max_length=128
    )
    reason: str | None = Field(default=None, min_length=1, max_length=2_000)
    expected_version: int | None = Field(
        default=None, alias="expectedVersion", ge=1
    )


class CancelPaymentRequest(ClosedModel):
    reason: str = Field(min_length=1, max_length=2_000)
    provider_reference: str | None = Field(
        default=None, alias="providerReference", min_length=1, max_length=128
    )
    provider_status: PaymentStatus | None = Field(
        default=None, alias="providerStatus"
    )
    expected_version: int | None = Field(
        default=None, alias="expectedVersion", ge=1
    )


class RefundPaymentRequest(ClosedModel):
    amount: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=2
    )
    amount_minor: int | None = Field(default=None, alias="amountMinor", gt=0)
    reason: str = Field(min_length=1, max_length=2_000)
    provider_refund_reference: str | None = Field(
        default=None,
        alias="providerRefundReference",
        min_length=1,
        max_length=128,
    )
    provider_status: PaymentStatus | None = Field(
        default=None, alias="providerStatus"
    )
    expected_version: int | None = Field(
        default=None, alias="expectedVersion", ge=1
    )

    def resolved_amount(self, currency: str) -> Decimal:
        if self.amount is None and self.amount_minor is None:
            raise ValueError("amount or amountMinor is required")
        from_minor = (
            amount_from_minor(self.amount_minor, currency)
            if self.amount_minor is not None
            else None
        )
        if (
            self.amount is not None
            and from_minor is not None
            and self.amount != from_minor
        ):
            raise ValueError("amount and amountMinor do not match")
        return self.amount or from_minor  # type: ignore[return-value]


class ReconcilePaymentRequest(ClosedModel):
    # All provider fields are optional: when providerStatus is absent, Payment
    # Service queries its provider-event ledger/mock adapter.
    provider_status: PaymentStatus | None = Field(
        default=None, alias="providerStatus"
    )
    provider_reference: str | None = Field(
        default=None, alias="providerReference", min_length=1, max_length=128
    )
    provider_refund_reference: str | None = Field(
        default=None,
        alias="providerRefundReference",
        min_length=1,
        max_length=128,
    )
    observed_refunded_amount: Decimal | None = Field(
        default=None,
        alias="observedRefundedAmount",
        ge=0,
        max_digits=18,
        decimal_places=2,
    )
    failure_code: str | None = Field(
        default=None, alias="failureCode", min_length=1, max_length=128
    )
    reason: str | None = Field(default=None, min_length=1, max_length=2_000)
    expected_version: int | None = Field(
        default=None, alias="expectedVersion", ge=1
    )


class ProviderCallbackRequest(ClosedModel):
    event_id: str = Field(alias="eventId", min_length=1, max_length=128)
    payment_id: str = Field(alias="paymentId", min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=40)
    operation: ProviderOperation
    provider_status: PaymentStatus = Field(alias="providerStatus")
    provider_reference: str | None = Field(
        default=None, alias="providerReference", min_length=1, max_length=128
    )
    provider_refund_reference: str | None = Field(
        default=None,
        alias="providerRefundReference",
        min_length=1,
        max_length=128,
    )
    amount: Decimal | None = Field(
        default=None, gt=0, max_digits=18, decimal_places=2
    )
    amount_minor: int | None = Field(default=None, alias="amountMinor", gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    observed_refunded_amount: Decimal | None = Field(
        default=None,
        alias="observedRefundedAmount",
        ge=0,
        max_digits=18,
        decimal_places=2,
    )
    failure_code: str | None = Field(
        default=None, alias="failureCode", min_length=1, max_length=128
    )
    reason: str | None = Field(default=None, min_length=1, max_length=2_000)
    occurred_at: datetime = Field(alias="occurredAt")

    @field_validator("currency")
    @classmethod
    def uppercase_optional_currency(cls, value: str | None) -> str | None:
        return value.upper() if value else value

    @model_validator(mode="after")
    def validate_callback_money(self) -> ProviderCallbackRequest:
        has_money = self.amount is not None or self.amount_minor is not None
        if has_money and self.currency is None:
            raise ValueError("currency is required when callback money is supplied")
        if self.currency is not None and not has_money:
            raise ValueError("amount or amountMinor is required with currency")
        if self.amount is not None and self.amount_minor is not None:
            converted = amount_from_minor(self.amount_minor, str(self.currency))
            if self.amount != converted:
                raise ValueError("amount and amountMinor do not match")
        return self

    def resolved_amount(self) -> Decimal | None:
        if self.amount is not None:
            return self.amount
        if self.amount_minor is not None and self.currency is not None:
            return amount_from_minor(self.amount_minor, self.currency)
        return None


class ProviderEventQuery(ClosedModel):
    payment_id: str = Field(alias="paymentId", min_length=1, max_length=128)
