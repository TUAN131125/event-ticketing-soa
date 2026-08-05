"""Closed canonical Payment request schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MoneyRequest(ClosedModel):
    amount_minor: int = Field(alias="amountMinor", ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class CreatePaymentRequest(ClosedModel):
    booking_id: str = Field(alias="bookingId", min_length=1, max_length=128)
    amount: MoneyRequest
    method_token: str = Field(alias="methodToken", min_length=6, max_length=200)


class RefundPaymentRequest(ClosedModel):
    amount: MoneyRequest
    reason: str = Field(max_length=300)


class ProviderCallbackRequest(ClosedModel):
    event_id: str = Field(alias="eventId")
    payment_id: str = Field(alias="paymentId")
    provider_status: str = Field(alias="providerStatus")
    occurred_at: datetime = Field(alias="occurredAt")

    @field_validator("occurred_at")
    @classmethod
    def utc_only(cls, value: datetime) -> datetime:
        offset = value.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            raise ValueError("occurredAt must be UTC")
        return value
