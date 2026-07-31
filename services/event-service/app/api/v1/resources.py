"""REST endpoint doc/ghi thong tin su kien."""
from fastapi import APIRouter, Depends, status

from app.application.commands.create_event import create_event
from app.application.commands.get_event import get_event
from app.application.commands.list_events import list_events
from app.application.commands.update_event import update_event
from app.dependencies import get_repository
from app.domain.value_objects import TicketType
from app.repositories.interfaces import EventRepository
from app.schemas.requests import EventCreateRequest, EventUpdateRequest
from app.schemas.responses import EventResponse

router = APIRouter(prefix="/events", tags=["events"])


@router.get("", response_model=list[EventResponse])
def list_all(repo: EventRepository = Depends(get_repository)):
    return [EventResponse.from_entity(e) for e in list_events(repo)]


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def create(payload: EventCreateRequest, repo: EventRepository = Depends(get_repository)):
    ticket_types = [TicketType(t.type, t.price) for t in payload.ticketTypes]
    event = create_event(repo, payload.name, payload.location, payload.startTime, ticket_types)
    return EventResponse.from_entity(event)


@router.get("/{event_id}", response_model=EventResponse)
def get(event_id: str, repo: EventRepository = Depends(get_repository)):
    event = get_event(repo, event_id)
    return EventResponse.from_entity(event)


@router.put("/{event_id}", response_model=EventResponse)
def update(event_id: str, payload: EventUpdateRequest, repo: EventRepository = Depends(get_repository)):
    event = update_event(repo, event_id, name=payload.name, location=payload.location,
                          start_time=payload.startTime)
    return EventResponse.from_entity(event)


@router.get("/{event_id}/on-sale")
def is_on_sale(event_id: str, repo: EventRepository = Depends(get_repository)):
    """Endpoint tien loi de ESB kiem tra nhanh su kien co dang mo ban khong."""
    event = get_event(repo, event_id)
    return {"onSale": event.status.value == "ON_SALE"}
