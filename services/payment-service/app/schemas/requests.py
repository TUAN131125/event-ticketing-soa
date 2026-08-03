"""Closed request contracts for payment commands."""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.enums import PaymentStatus


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CreatePaymentRequest(ClosedModel):
    booking_id: str = Field(alias="bookingId", min_length=1, max_length=128)
    customer_id: str = Field(alias="customerId", min_length=1, max_length=128)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    currency: str = Field(min_length=3, max_length=3)
    payment_method: str = Field(alias="paymentMethod", min_length=1, max_length=40)
    provider: str = Field(min_length=1, max_length=40)

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, value: str) -> str:
        return value.upper()


class AuthorizePaymentRequest(ClosedModel):
    approved: bool
    provider_reference: str | None = Field(
        default=None, alias="providerReference", min_length=1, max_length=128
    )
    failure_code: str | None = Field(
        default=None, alias="failureCode", min_length=1, max_length=128
    )
    reason: str | None = Field(default=None, min_length=1, max_length=2_000)
    expected_version: int = Field(alias="expectedVersion", ge=1)


class CapturePaymentRequest(ClosedModel):
    succeeded: bool
    provider_reference: str = Field(
        alias="providerReference", min_length=1, max_length=128
    )
    failure_code: str | None = Field(
        default=None, alias="failureCode", min_length=1, max_length=128
    )
    reason: str | None = Field(default=None, min_length=1, max_length=2_000)
    expected_version: int = Field(alias="expectedVersion", ge=1)


class CancelPaymentRequest(ClosedModel):
    reason: str = Field(min_length=1, max_length=2_000)
    provider_reference: str | None = Field(
        default=None, alias="providerReference", min_length=1, max_length=128
    )
    expected_version: int = Field(alias="expectedVersion", ge=1)


class RefundPaymentRequest(ClosedModel):
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    reason: str = Field(min_length=1, max_length=2_000)
    provider_refund_reference: str = Field(
        alias="providerRefundReference", min_length=1, max_length=128
    )
    expected_version: int = Field(alias="expectedVersion", ge=1)


class ReconcilePaymentRequest(ClosedModel):
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
    expected_version: int = Field(alias="expectedVersion", ge=1)
