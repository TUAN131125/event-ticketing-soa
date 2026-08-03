"""Ticket cancellation, QR rotation and venue check-in commands."""

from fastapi import APIRouter, Depends, Header

from app.application.service import TicketService
from app.dependencies import get_service
from app.domain.value_objects import RequestContext
from app.middleware.authentication import require_internal_caller
from app.observability.metrics import COMMAND_TOTAL
from app.schemas.requests import (
    CancelTicketRequest,
    CheckInTicketRequest,
    RegenerateQrRequest,
)
from app.schemas.responses import TicketResponse

router = APIRouter(prefix="/tickets", tags=["ticket-commands"])


@router.post(
    "/{ticket_id}/cancel",
    response_model=TicketResponse,
    operation_id="cancelTicket",
)
def cancel(
    ticket_id: str,
    body: CancelTicketRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=128
    ),
    context: RequestContext = Depends(require_internal_caller),
    service: TicketService = Depends(get_service),
) -> TicketResponse:
    try:
        ticket = service.cancel(
            context,
            idempotency_key=idempotency_key,
            ticket_id=ticket_id,
            reason=body.reason,
            expected_version=body.expected_version,
        )
        COMMAND_TOTAL.labels("cancel", "success").inc()
        return TicketResponse.from_entity_with_qr(
            ticket, service.settings.qr_signing_key
        )
    except Exception:
        COMMAND_TOTAL.labels("cancel", "failure").inc()
        raise


@router.post(
    "/{ticket_id}/check-in",
    response_model=TicketResponse,
    operation_id="checkInTicket",
)
def check_in(
    ticket_id: str,
    body: CheckInTicketRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=128
    ),
    context: RequestContext = Depends(require_internal_caller),
    service: TicketService = Depends(get_service),
) -> TicketResponse:
    try:
        ticket = service.check_in(
            context,
            idempotency_key=idempotency_key,
            ticket_id=ticket_id,
            qr_token=body.qr_token,
            gate_id=body.gate_id,
            expected_version=body.expected_version,
        )
        COMMAND_TOTAL.labels("check_in", "success").inc()
        return TicketResponse.from_entity_with_qr(
            ticket, service.settings.qr_signing_key
        )
    except Exception:
        COMMAND_TOTAL.labels("check_in", "failure").inc()
        raise


@router.post(
    "/{ticket_id}/qr/regenerate",
    response_model=TicketResponse,
    operation_id="regenerateTicketQr",
)
def regenerate(
    ticket_id: str,
    body: RegenerateQrRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=128
    ),
    context: RequestContext = Depends(require_internal_caller),
    service: TicketService = Depends(get_service),
) -> TicketResponse:
    try:
        ticket = service.regenerate_qr(
            context,
            idempotency_key=idempotency_key,
            ticket_id=ticket_id,
            expected_version=body.expected_version,
        )
        COMMAND_TOTAL.labels("regenerate_qr", "success").inc()
        return TicketResponse.from_entity_with_qr(
            ticket, service.settings.qr_signing_key
        )
    except Exception:
        COMMAND_TOTAL.labels("regenerate_qr", "failure").inc()
        raise
