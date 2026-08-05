"""Canonical public Event queries and protected writes."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Path,
    Query,
    Response,
    status,
)
from libs.platform_http import etag, parse_if_match

from app.application.commands.create_event import create_event
from app.application.commands.get_event import get_event
from app.application.commands.list_events import list_events
from app.application.commands.update_event import update_event
from app.dependencies import get_repository
from app.domain.enums import EventStatus
from app.domain.value_objects import Money, TicketType
from app.middleware.authentication import require_service_principal
from app.repositories.interfaces import EventRepository
from app.schemas.requests import EventCreateRequest
from app.schemas.responses import EventResponse, SaleEligibilityResponse

router = APIRouter(prefix="/events", tags=["events"])


def _ticket_types(payload: EventCreateRequest) -> list[TicketType]:
    return [
        TicketType(
            item.code,
            item.name,
            Money(item.price.amount_minor, item.price.currency),
        )
        for item in payload.ticket_types
    ]


def _version(value: str) -> int:
    try:
        return parse_if_match(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="If-Match is invalid") from exc


@router.get("", response_model=list[EventResponse], operation_id="listEvents")
def list_all(
    event_status: EventStatus | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    repo: EventRepository = Depends(get_repository),
) -> list[EventResponse]:
    events = list(list_events(repo))
    if event_status is not None:
        events = [item for item in events if item.status == event_status]
    start = (page - 1) * 100
    return [EventResponse.from_entity(item) for item in events[start : start + 100]]


@router.post(
    "",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id="createEvent",
    dependencies=[Depends(require_service_principal)],
)
def create(
    payload: EventCreateRequest,
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    repo: EventRepository = Depends(get_repository),
) -> EventResponse:
    event = create_event(
        repo,
        payload.name,
        payload.venue,
        payload.starts_at,
        payload.sale_starts_at,
        payload.sale_ends_at,
        _ticket_types(payload),
    )
    response.headers["ETag"] = etag(event.resource_version)
    return EventResponse.from_entity(event)


@router.get("/{eventId}", response_model=EventResponse, operation_id="getEvent")
def get(
    event_id: Annotated[str, Path(alias="eventId")],
    response: Response,
    repo: EventRepository = Depends(get_repository),
) -> EventResponse:
    event = get_event(repo, event_id)
    response.headers["ETag"] = etag(event.resource_version)
    return EventResponse.from_entity(event)


@router.put(
    "/{eventId}",
    response_model=EventResponse,
    operation_id="replaceEvent",
    dependencies=[Depends(require_service_principal)],
)
def replace(
    event_id: Annotated[str, Path(alias="eventId")],
    payload: EventCreateRequest,
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    if_match: Annotated[str, Header(alias="If-Match", pattern=r'^"[1-9][0-9]*"$')],
    repo: EventRepository = Depends(get_repository),
) -> EventResponse:
    event = update_event(
        repo,
        event_id,
        name=payload.name,
        venue=payload.venue,
        starts_at=payload.starts_at,
        sale_starts_at=payload.sale_starts_at,
        sale_ends_at=payload.sale_ends_at,
        ticket_types=_ticket_types(payload),
        expected_version=_version(if_match),
    )
    response.headers["ETag"] = etag(event.resource_version)
    return EventResponse.from_entity(event)


@router.get(
    "/{eventId}/sale-eligibility",
    response_model=SaleEligibilityResponse,
    operation_id="getSaleEligibility",
    dependencies=[Depends(require_service_principal)],
)
def sale_eligibility(
    event_id: Annotated[str, Path(alias="eventId")],
    repo: EventRepository = Depends(get_repository),
) -> SaleEligibilityResponse:
    event = get_event(repo, event_id)
    now = datetime.now(UTC)
    eligible = (
        event.status == EventStatus.ON_SALE
        and event.sale_starts_at <= now <= event.sale_ends_at
    )
    return SaleEligibilityResponse(
        eventId=event.id,
        eligible=eligible,
        status=event.status.value,
        reasonCode=None if eligible else "EVENT_NOT_ON_SALE",
        priceSnapshot=[
            {
                "code": item.code,
                "name": item.name,
                "price": {
                    "amountMinor": item.price.amount_minor,
                    "currency": item.price.currency,
                },
            }
            for item in event.ticket_types
        ],
    )
