"""Endpoint quan tri: dieu khien vong doi ban ve cua su kien."""
from fastapi import APIRouter, Depends

from app.application.commands.cancel_event import cancel_event
from app.application.commands.close_sales import close_sales
from app.application.commands.open_sales import open_sales
from app.application.commands.pause_sales import pause_sales
from app.dependencies import get_repository
from app.repositories.interfaces import EventRepository
from app.schemas.responses import EventResponse

router = APIRouter(prefix="/events", tags=["admin"])


@router.post("/{event_id}/open-sales", response_model=EventResponse)
def open_sales_endpoint(event_id: str, repo: EventRepository = Depends(get_repository)):
    return EventResponse.from_entity(open_sales(repo, event_id))


@router.post("/{event_id}/pause-sales", response_model=EventResponse)
def pause_sales_endpoint(event_id: str, repo: EventRepository = Depends(get_repository)):
    return EventResponse.from_entity(pause_sales(repo, event_id))


@router.post("/{event_id}/close-sales", response_model=EventResponse)
def close_sales_endpoint(event_id: str, repo: EventRepository = Depends(get_repository)):
    return EventResponse.from_entity(close_sales(repo, event_id))


@router.post("/{event_id}/cancel", response_model=EventResponse)
def cancel_event_endpoint(event_id: str, repo: EventRepository = Depends(get_repository)):
    return EventResponse.from_entity(cancel_event(repo, event_id))
