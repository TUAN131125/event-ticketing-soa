"""Pydantic response schema - khop Event/SaleEligibility trong OpenAPI."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.domain.entities import Event


class MoneyResponse(BaseModel):
    amountMinor: int
    currency: str


class TicketTypeResponse(BaseModel):
    code: str
    name: str
    price: MoneyResponse


class EventResponse(BaseModel):
    eventId: str
    name: str
    venue: str
    startsAt: datetime
    saleStartsAt: datetime
    saleEndsAt: datetime
    status: str
    ticketTypes: list[TicketTypeResponse]
    resourceVersion: int

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
                    code=t.code,
                    name=t.name,
                    price=MoneyResponse(
                        amountMinor=t.price.amount_minor, currency=t.price.currency
                    ),
                )
                for t in event.ticket_types
            ],
            resourceVersion=event.resource_version,
        )


class SaleEligibilityResponse(BaseModel):
    eventId: str
    eligible: bool
    status: str
    reasonCode: str | None = None
    priceSnapshot: list[TicketTypeResponse]


class EventListResponse(BaseModel):
    """Khong nam trong OpenAPI (listEvents tra ve mang thuan tuy), dung
    noi bo de truyen ca totalItems cho router tinh header phan trang."""

    items: list[EventResponse]
    total: int
