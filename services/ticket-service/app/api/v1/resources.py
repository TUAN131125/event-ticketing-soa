"""Internal ticket issuance and query endpoints."""

from fastapi import APIRouter, Depends, Header, Query, status

from app.application.service import TicketService
from app.dependencies import get_service
from app.domain.enums import TicketStatus
from app.domain.value_objects import RequestContext, TicketDefinition
from app.middleware.authentication import require_internal_caller
from app.observability.metrics import COMMAND_TOTAL
from app.schemas.requests import IssueTicketsRequest
from app.schemas.responses import (
    TicketBatchResponse,
    TicketPageResponse,
    TicketResponse,
)

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post(
    "/issue",
    response_model=TicketBatchResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="issueTickets",
)
def issue(
    body: IssueTicketsRequest,
    idempotency_key: str = Header(
        alias="Idempotency-Key", min_length=1, max_length=128
    ),
    context: RequestContext = Depends(require_internal_caller),
    service: TicketService = Depends(get_service),
) -> TicketBatchResponse:
    try:
        tickets = service.issue(
            context,
            idempotency_key=idempotency_key,
            booking_id=body.booking_id,
            customer_id=body.customer_id,
            event_id=body.event_id,
            payment_id=body.payment_id,
            definitions=tuple(
                TicketDefinition(
                    seat_id=item.seat_id,
                    seat_label=item.seat_label or item.seat_id,
                    ticket_type=item.ticket_type,
                )
                for item in body.tickets
            ),
        )
        COMMAND_TOTAL.labels("issue", "success").inc()
        return TicketBatchResponse.from_entities(
            tickets, service.settings.qr_signing_key
        )
    except Exception:
        COMMAND_TOTAL.labels("issue", "failure").inc()
        raise


@router.get("", response_model=TicketPageResponse, operation_id="listTickets")
def list_all(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, alias="pageSize", ge=1, le=100),
    booking_id: str | None = Query(default=None, alias="bookingId"),
    customer_id: str | None = Query(default=None, alias="customerId"),
    event_id: str | None = Query(default=None, alias="eventId"),
    ticket_status: TicketStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, min_length=1, max_length=128),
    _context: RequestContext = Depends(require_internal_caller),
    service: TicketService = Depends(get_service),
) -> TicketPageResponse:
    return TicketPageResponse.from_page(
        service.list(
            page=page,
            page_size=page_size,
            booking_id=booking_id,
            customer_id=customer_id,
            event_id=event_id,
            status=ticket_status,
            search=search,
        )
    )


@router.get("/{ticket_id}", response_model=TicketResponse, operation_id="getTicket")
def get(
    ticket_id: str,
    _context: RequestContext = Depends(require_internal_caller),
    service: TicketService = Depends(get_service),
) -> TicketResponse:
    return TicketResponse.from_entity_with_qr(
        service.get(ticket_id), service.settings.qr_signing_key
    )
