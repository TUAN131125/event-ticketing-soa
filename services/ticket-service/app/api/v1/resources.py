"""Canonical Ticket issuance, query and validation endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Response, status
from libs.platform_http import etag

from app.application.service import TicketService
from app.dependencies import get_service
from app.domain.value_objects import RequestContext, TicketDefinition
from app.middleware.authentication import require_internal_caller
from app.schemas.requests import IssueTicketsRequest, ValidateTicketRequest
from app.schemas.responses import TicketResponse
from app.security.qr_tokens import verify_qr_token

router = APIRouter(tags=["tickets"])


@router.post(
    "/tickets:issue",
    response_model=list[TicketResponse],
    status_code=status.HTTP_201_CREATED,
    operation_id="issueTickets",
)
def issue(
    body: IssueTicketsRequest,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    context: RequestContext = Depends(require_internal_caller),
    service: TicketService = Depends(get_service),
) -> list[TicketResponse]:
    tickets = service.issue(
        context,
        idempotency_key=idempotency_key,
        booking_id=body.booking_id,
        customer_id=body.customer_id,
        event_id=body.event_id,
        payment_id="CAPTURED",
        definitions=tuple(
            TicketDefinition(
                seat_id=item.seat_id,
                seat_label=item.seat_id,
                ticket_type="STANDARD",
            )
            for item in body.items
        ),
    )
    return [
        TicketResponse.from_entity(ticket, service.settings.qr_signing_key)
        for ticket in tickets
    ]


@router.get(
    "/tickets/{ticketId}",
    response_model=TicketResponse,
    operation_id="getTicket",
)
def get(
    ticket_id: Annotated[str, Path(alias="ticketId")],
    response: Response,
    context: RequestContext = Depends(require_internal_caller),
    service: TicketService = Depends(get_service),
) -> TicketResponse:
    ticket = service.get(ticket_id)
    response.headers["ETag"] = etag(ticket.resource_version)
    return TicketResponse.from_entity(ticket, service.settings.qr_signing_key)


@router.get(
    "/bookings/{bookingId}/tickets",
    response_model=list[TicketResponse],
    operation_id="listBookingTickets",
)
def by_booking(
    booking_id: Annotated[str, Path(alias="bookingId")],
    context: RequestContext = Depends(require_internal_caller),
    service: TicketService = Depends(get_service),
) -> list[TicketResponse]:
    page = service.list(
        page=1,
        page_size=100,
        booking_id=booking_id,
        customer_id=None,
        event_id=None,
        status=None,
        search=None,
    )
    return [
        TicketResponse.from_entity(ticket, service.settings.qr_signing_key)
        for ticket in page.items
    ]


@router.post(
    "/tickets/validate",
    response_model=TicketResponse,
    operation_id="validateTicket",
)
def validate(
    body: ValidateTicketRequest,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    context: RequestContext = Depends(require_internal_caller),
    service: TicketService = Depends(get_service),
) -> TicketResponse:
    parts = body.qr_token.split(".")
    if len(parts) != 4:
        from app.domain.exceptions import InvalidQrToken

        raise InvalidQrToken()
    ticket = service.get(parts[1])
    verify_qr_token(
        body.qr_token,
        expected_ticket_id=ticket.ticket_id,
        expected_qr_version=ticket.qr_version,
        signing_key=service.settings.qr_signing_key,
    )
    return TicketResponse.from_entity(ticket, service.settings.qr_signing_key)
