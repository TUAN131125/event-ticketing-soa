"""Canonical Ticket check-in, cancellation and QR reissue commands."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Response
from libs.platform_http import etag, parse_if_match

from app.application.service import TicketService
from app.dependencies import get_service
from app.domain.value_objects import RequestContext
from app.middleware.authentication import require_internal_caller
from app.schemas.responses import TicketResponse
from app.security.qr_tokens import create_qr_token

router = APIRouter(prefix="/tickets", tags=["ticket-commands"])


def _headers(
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    if_match: Annotated[str, Header(alias="If-Match", pattern=r'^"[1-9][0-9]*"$')],
) -> tuple[str, int]:
    return idempotency_key, parse_if_match(if_match)


@router.post(
    "/{ticketId}/check-in", response_model=TicketResponse, operation_id="checkInTicket"
)
def check_in(
    ticket_id: Annotated[str, Path(alias="ticketId")],
    response: Response,
    headers: tuple[str, int] = Depends(_headers),
    context: RequestContext = Depends(require_internal_caller),
    service: TicketService = Depends(get_service),
) -> TicketResponse:
    current = service.get(ticket_id)
    token = create_qr_token(
        ticket_id, current.qr_version, service.settings.qr_signing_key
    )
    ticket = service.check_in(
        context,
        idempotency_key=headers[0],
        ticket_id=ticket_id,
        qr_token=token,
        gate_id=context.caller_service,
        expected_version=headers[1],
    )
    response.headers["ETag"] = etag(ticket.resource_version)
    return TicketResponse.from_entity(ticket, service.settings.qr_signing_key)


@router.post(
    "/{ticketId}/cancel", response_model=TicketResponse, operation_id="cancelTicket"
)
def cancel(
    ticket_id: Annotated[str, Path(alias="ticketId")],
    response: Response,
    headers: tuple[str, int] = Depends(_headers),
    context: RequestContext = Depends(require_internal_caller),
    service: TicketService = Depends(get_service),
) -> TicketResponse:
    ticket = service.cancel(
        context,
        idempotency_key=headers[0],
        ticket_id=ticket_id,
        reason="Booking workflow cancelled",
        expected_version=headers[1],
    )
    response.headers["ETag"] = etag(ticket.resource_version)
    return TicketResponse.from_entity(ticket, service.settings.qr_signing_key)


@router.post(
    "/{ticketId}/reissue-qr", response_model=TicketResponse, operation_id="reissueQr"
)
def reissue(
    ticket_id: Annotated[str, Path(alias="ticketId")],
    response: Response,
    headers: tuple[str, int] = Depends(_headers),
    context: RequestContext = Depends(require_internal_caller),
    service: TicketService = Depends(get_service),
) -> TicketResponse:
    ticket = service.regenerate_qr(
        context,
        idempotency_key=headers[0],
        ticket_id=ticket_id,
        expected_version=headers[1],
    )
    response.headers["ETag"] = etag(ticket.resource_version)
    return TicketResponse.from_entity(ticket, service.settings.qr_signing_key)
