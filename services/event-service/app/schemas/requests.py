"""Pydantic request schema - khop EventCreate trong OpenAPI (dung chung
cho POST /events va PUT /events/{id}, vi PUT la "replace toan bo")."""

from datetime import datetime

from pydantic import BaseModel, Field


class MoneyRequest(BaseModel):
    amountMinor: int = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$", default="VND")


class TicketTypeRequest(BaseModel):
    code: str
    name: str
    price: MoneyRequest


class EventCreateRequest(BaseModel):
    name: str = Field(min_length=2)
    venue: str
    startsAt: datetime
    saleStartsAt: datetime
    saleEndsAt: datetime
    ticketTypes: list[TicketTypeRequest] = Field(min_length=1)
