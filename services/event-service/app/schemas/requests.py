"""Closed canonical Event request schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MoneyRequest(ClosedModel):
    amount_minor: int = Field(alias="amountMinor", ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class TicketTypeRequest(ClosedModel):
    code: str = Field(min_length=1)
    name: str = Field(min_length=1)
    price: MoneyRequest


class EventCreateRequest(ClosedModel):
    name: str = Field(min_length=2)
    venue: str = Field(min_length=1)
    starts_at: datetime = Field(alias="startsAt")
    sale_starts_at: datetime = Field(alias="saleStartsAt")
    sale_ends_at: datetime = Field(alias="saleEndsAt")
    ticket_types: list[TicketTypeRequest] = Field(alias="ticketTypes", min_length=1)

    @field_validator("starts_at", "sale_starts_at", "sale_ends_at")
    @classmethod
    def require_utc(cls, value: datetime) -> datetime:
        offset = value.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            raise ValueError("Event timestamps must be UTC")
        return value
