"""Canonical Payment response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import Payment
from app.domain.value_objects import Refund


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MoneyResponse(ResponseModel):
    amount_minor: int = Field(alias="amountMinor", ge=0)
    currency: str


class PaymentResponse(ResponseModel):
    payment_id: str = Field(alias="paymentId")
    booking_id: str = Field(alias="bookingId")
    amount: MoneyResponse
    status: str
    provider_reference: str | None = Field(default=None, alias="providerReference")
    resource_version: int = Field(alias="resourceVersion", ge=1)
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    @classmethod
    def from_entity(cls, payment: Payment) -> PaymentResponse:
        status = (
            "CREATED" if payment.status.value == "PENDING" else payment.status.value
        )
        return cls(
            paymentId=payment.payment_id,
            bookingId=payment.booking_id,
            amount=MoneyResponse(
                amountMinor=int(payment.amount), currency=payment.currency
            ),
            status=status,
            providerReference=payment.provider_reference,
            resourceVersion=payment.resource_version,
            createdAt=payment.created_at,
            updatedAt=payment.updated_at,
        )


class RefundResponse(ResponseModel):
    refund_id: str = Field(alias="refundId")
    payment_id: str = Field(alias="paymentId")
    amount: MoneyResponse
    reason: str
    provider_reference: str = Field(alias="providerReference")
    created_at: datetime = Field(alias="createdAt")

    @classmethod
    def from_value(cls, refund: Refund) -> RefundResponse:
        return cls(
            refundId=refund.refund_id,
            paymentId=refund.payment_id,
            amount=MoneyResponse(
                amountMinor=int(refund.amount), currency=refund.currency
            ),
            reason=refund.reason,
            providerReference=refund.provider_reference,
            createdAt=refund.created_at,
        )
