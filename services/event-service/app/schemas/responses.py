"""Canonical Event response schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import Event


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class MoneyResponse(ResponseModel):
    amount_minor: int = Field(alias="amountMinor")
    currency: str


class TicketTypeResponse(ResponseModel):
    code: str
    name: str
    price: MoneyResponse


class EventResponse(ResponseModel):
    event_id: str = Field(alias="eventId")
    name: str
    venue: str
    starts_at: datetime = Field(alias="startsAt")
    sale_starts_at: datetime | None = Field(default=None, alias="saleStartsAt")
    sale_ends_at: datetime | None = Field(default=None, alias="saleEndsAt")
    status: str
    ticket_types: list[TicketTypeResponse] = Field(alias="ticketTypes")
    resource_version: int = Field(alias="resourceVersion", ge=1)

    @classmethod
    def from_entity(cls, event: Event) -> EventResponse:
        return cls(
            eventId=event.id,
            name=event.name,
            venue=event.venue,
            startsAt=event.starts_at,
            saleStartsAt=event.sale_starts_at,
            saleEndsAt=event.sale_ends_at,
            status=event.status.value,
            ticketTypes=[
                TicketTypeResponse(
                    code=item.code,
                    name=item.name,
                    price=MoneyResponse(
                        amountMinor=item.price.amount_minor,
                        currency=item.price.currency,
                    ),
                )
                for item in event.ticket_types
            ],
            resourceVersion=event.resource_version,
        )


class SaleEligibilityResponse(ResponseModel):
    event_id: str = Field(alias="eventId")
    eligible: bool
    status: str
    reason_code: str | None = Field(default=None, alias="reasonCode")
    price_snapshot: list[dict[str, object]] = Field(
        default_factory=list, alias="priceSnapshot"
    )
