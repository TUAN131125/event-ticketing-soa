"""Ticket response contracts and QR presentation."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.entities import Ticket
from app.domain.enums import TicketStatus
from app.domain.value_objects import TicketPage
from app.security.qr_tokens import create_qr_token, qr_code_data_uri


class ResponseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class TicketSummaryResponse(ResponseModel):
    id: str
    ticket_id: str = Field(alias="ticketId")
    booking_id: str = Field(alias="bookingId")
    customer_id: str = Field(alias="customerId")
    event_id: str = Field(alias="eventId")
    payment_id: str = Field(alias="paymentId")
    seat_id: str = Field(alias="seatId")
    seat_label: str = Field(alias="seatLabel")
    ticket_type: str = Field(alias="ticketType")
    status: TicketStatus
    qr_version: int = Field(alias="qrVersion")
    resource_version: int = Field(alias="resourceVersion")
    issued_at: datetime = Field(alias="issuedAt")
    updated_at: datetime = Field(alias="updatedAt")
    checked_in_at: datetime | None = Field(default=None, alias="checkedInAt")
    checked_in_gate_id: str | None = Field(default=None, alias="checkedInGateId")
    checked_in_by: str | None = Field(default=None, alias="checkedInBy")
    cancelled_at: datetime | None = Field(default=None, alias="cancelledAt")
    cancellation_reason: str | None = Field(default=None, alias="cancellationReason")

    @classmethod
    def from_entity(cls, ticket: Ticket) -> TicketSummaryResponse:
        return cls(
            id=ticket.ticket_id,
            ticketId=ticket.ticket_id,
            bookingId=ticket.booking_id,
            customerId=ticket.customer_id,
            eventId=ticket.event_id,
            paymentId=ticket.payment_id,
            seatId=ticket.seat_id,
            seatLabel=ticket.seat_label,
            ticketType=ticket.ticket_type,
            status=ticket.status,
            qrVersion=ticket.qr_version,
            resourceVersion=ticket.resource_version,
            issuedAt=ticket.issued_at,
            updatedAt=ticket.updated_at,
            checkedInAt=ticket.checked_in_at,
            checkedInGateId=ticket.checked_in_gate_id,
            checkedInBy=ticket.checked_in_by,
            cancelledAt=ticket.cancelled_at,
            cancellationReason=ticket.cancellation_reason,
        )


class TicketResponse(TicketSummaryResponse):
    qr_code: str | None = Field(default=None, alias="qrCode")

    @classmethod
    def from_entity_with_qr(cls, ticket: Ticket, signing_key: str) -> TicketResponse:
        summary = TicketSummaryResponse.from_entity(ticket)
        qr_code = None
        if ticket.status == TicketStatus.VALID:
            token = create_qr_token(ticket.ticket_id, ticket.qr_version, signing_key)
            qr_code = qr_code_data_uri(token)
        return cls(**summary.model_dump(by_alias=True), qrCode=qr_code)


class TicketBatchResponse(ResponseModel):
    items: list[TicketResponse]

    @classmethod
    def from_entities(
        cls, tickets: tuple[Ticket, ...], signing_key: str
    ) -> TicketBatchResponse:
        return cls(
            items=[
                TicketResponse.from_entity_with_qr(ticket, signing_key)
                for ticket in tickets
            ]
        )


class TicketPageResponse(ResponseModel):
    items: list[TicketSummaryResponse]
    page: int
    page_size: int = Field(alias="pageSize")
    total: int
    total_pages: int = Field(alias="totalPages")

    @classmethod
    def from_page(cls, result: TicketPage) -> TicketPageResponse:
        return cls(
            items=[
                TicketSummaryResponse.from_entity(ticket) for ticket in result.items
            ],
            page=result.page,
            pageSize=result.page_size,
            total=result.total,
            totalPages=result.total_pages,
        )
