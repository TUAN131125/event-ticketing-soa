"""Canonical Event lifecycle commands."""

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Path, Response
from libs.platform_http import etag

from app.api.v1.resources import _version
from app.application.commands.cancel_event import cancel_event
from app.application.commands.close_event import close_event
from app.application.commands.open_sales import open_sales
from app.application.commands.pause_sales import pause_sales
from app.dependencies import get_repository
from app.domain.entities import Event
from app.middleware.authentication import require_service_principal
from app.repositories.interfaces import EventRepository
from app.schemas.responses import EventResponse

router = APIRouter(
    prefix="/events",
    tags=["event-commands"],
    dependencies=[Depends(require_service_principal)],
)


def _transition(
    command: Callable[[EventRepository, str, int | None], Event],
    repo: EventRepository,
    event_id: str,
    if_match: str,
    response: Response,
) -> EventResponse:
    event = command(repo, event_id, _version(if_match))
    response.headers["ETag"] = etag(event.resource_version)
    return EventResponse.from_entity(event)


@router.post(
    "/{eventId}/publish", response_model=EventResponse, operation_id="publishEvent"
)
def publish(
    event_id: Annotated[str, Path(alias="eventId")],
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    if_match: Annotated[str, Header(alias="If-Match", pattern=r'^"[1-9][0-9]*"$')],
    repo: EventRepository = Depends(get_repository),
) -> EventResponse:
    return _transition(open_sales, repo, event_id, if_match, response)


@router.post(
    "/{eventId}/pause", response_model=EventResponse, operation_id="pauseEvent"
)
def pause(
    event_id: Annotated[str, Path(alias="eventId")],
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    if_match: Annotated[str, Header(alias="If-Match", pattern=r'^"[1-9][0-9]*"$')],
    repo: EventRepository = Depends(get_repository),
) -> EventResponse:
    return _transition(pause_sales, repo, event_id, if_match, response)


@router.post(
    "/{eventId}/close", response_model=EventResponse, operation_id="closeEvent"
)
def close(
    event_id: Annotated[str, Path(alias="eventId")],
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    if_match: Annotated[str, Header(alias="If-Match", pattern=r'^"[1-9][0-9]*"$')],
    repo: EventRepository = Depends(get_repository),
) -> EventResponse:
    return _transition(close_event, repo, event_id, if_match, response)


@router.post(
    "/{eventId}/cancel", response_model=EventResponse, operation_id="cancelEvent"
)
def cancel(
    event_id: Annotated[str, Path(alias="eventId")],
    response: Response,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    if_match: Annotated[str, Header(alias="If-Match", pattern=r'^"[1-9][0-9]*"$')],
    repo: EventRepository = Depends(get_repository),
) -> EventResponse:
    return _transition(cancel_event, repo, event_id, if_match, response)
