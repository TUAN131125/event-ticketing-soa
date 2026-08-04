"""REST endpoint cua Event Service - khop endpoint baseline trong OpenAPI
Giai doan 5 (contracts/openapi/event-service.yaml)."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Header, Query, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.application.commands.cancel_event import cancel_event
from app.application.commands.create_event import create_event
from app.application.commands.get_event import get_event
from app.application.commands.get_sale_eligibility import get_sale_eligibility
from app.application.commands.list_events import list_events
from app.application.commands.pause_event import pause_event
from app.application.commands.publish_event import publish_event
from app.application.commands.replace_event import replace_event
from app.application.services.idempotency import run_idempotent
from app.dependencies import (
    get_audit_repository,
    get_idempotency_repository,
    get_repository,
)
from app.domain.enums import EventStatus
from app.domain.exceptions import InvalidEventDataError
from app.domain.value_objects import Money, TicketType
from app.repositories.interfaces import (
    AuditRepository,
    EventRepository,
    IdempotencyRepository,
)
from app.schemas.requests import EventCreateRequest
from app.schemas.responses import (
    EventResponse,
    MoneyResponse,
    SaleEligibilityResponse,
    TicketTypeResponse,
)

router = APIRouter(prefix="/events", tags=["events"])

IF_MATCH_PATTERN = re.compile(r'^"([0-9]+)"$')


def _actor_id(
    request: Request, x_actor_id: str | None = Header(default=None, alias="X-Actor-Id")
) -> str:
    """Chua co JWT/service-auth that trong MVP (xem middleware/authentication.py)
    - tam thoi lay tu header tuy chon, mac dinh 'admin', chi dung de ghi
    audit (EVT-11), khong dung de cap quyen thuc."""
    return x_actor_id or "admin"


def _parse_if_match(if_match: str) -> int:
    match = IF_MATCH_PATTERN.match(if_match)
    if not match:
        raise InvalidEventDataError('If-Match phai co dang "<so>", vi du "3"')
    return int(match.group(1))


def _to_ticket_types(payload: EventCreateRequest) -> list[TicketType]:
    return [
        TicketType(t.code, t.name, Money(t.price.amountMinor, t.price.currency))
        for t in payload.ticketTypes
    ]


@router.get("")
def list_all(
    status: EventStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
    repo: EventRepository = Depends(get_repository),
):
    """EVT-03. OpenAPI khai bao response la mang thuan tuy (khong bao
    PageMeta) - tong so ban ghi duoc tra qua header X-Total-Count de
    khong pha vo shape da cong bo."""
    events, total = list_events(repo, status, page, pageSize)
    body = jsonable_encoder([EventResponse.from_entity(e) for e in events])
    return JSONResponse(content=body, headers={"X-Total-Count": str(total)})


@router.post("", status_code=201)
def create(
    payload: EventCreateRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    repo: EventRepository = Depends(get_repository),
    idem_repo: IdempotencyRepository = Depends(get_idempotency_repository),
    audit_repo: AuditRepository = Depends(get_audit_repository),
    actor_id: str = Depends(_actor_id),
):
    scope = f"create:{idempotency_key}"

    def execute() -> tuple[int, dict]:
        event = create_event(
            repo,
            audit_repo,
            actor_id,
            payload.name,
            payload.venue,
            payload.startsAt,
            payload.saleStartsAt,
            payload.saleEndsAt,
            _to_ticket_types(payload),
        )
        return 201, jsonable_encoder(EventResponse.from_entity(event))

    status_code, body = run_idempotent(
        idem_repo, scope, payload.model_dump(mode="json"), execute
    )
    return JSONResponse(status_code=status_code, content=body)


@router.get("/{event_id}")
def get(event_id: str, repo: EventRepository = Depends(get_repository)):
    event = get_event(repo, event_id)
    return jsonable_encoder(EventResponse.from_entity(event))


@router.put("/{event_id}")
def replace(
    event_id: str,
    payload: EventCreateRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    if_match: str = Header(alias="If-Match"),
    repo: EventRepository = Depends(get_repository),
    idem_repo: IdempotencyRepository = Depends(get_idempotency_repository),
    audit_repo: AuditRepository = Depends(get_audit_repository),
    actor_id: str = Depends(_actor_id),
):
    expected_version = _parse_if_match(if_match)
    scope = f"replace:{event_id}:{idempotency_key}"

    def execute() -> tuple[int, dict]:
        event = replace_event(
            repo,
            audit_repo,
            actor_id,
            event_id,
            expected_version,
            payload.name,
            payload.venue,
            payload.startsAt,
            payload.saleStartsAt,
            payload.saleEndsAt,
            _to_ticket_types(payload),
        )
        return 200, jsonable_encoder(EventResponse.from_entity(event))

    status_code, body = run_idempotent(
        idem_repo, scope, payload.model_dump(mode="json"), execute
    )
    return JSONResponse(status_code=status_code, content=body)


def _mutation_endpoint(
    event_id: str,
    idempotency_key: str,
    if_match: str,
    repo: EventRepository,
    idem_repo: IdempotencyRepository,
    audit_repo: AuditRepository,
    actor_id: str,
    op_name: str,
    command,
):
    expected_version = _parse_if_match(if_match)
    scope = f"{op_name}:{event_id}:{idempotency_key}"

    def execute() -> tuple[int, dict]:
        event = command(repo, audit_repo, actor_id, event_id, expected_version)
        return 200, jsonable_encoder(EventResponse.from_entity(event))

    status_code, body = run_idempotent(
        idem_repo, scope, {"eventId": event_id, "ifMatch": expected_version}, execute
    )
    return JSONResponse(status_code=status_code, content=body)


@router.post("/{event_id}/publish")
def publish(
    event_id: str,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    if_match: str = Header(alias="If-Match"),
    repo: EventRepository = Depends(get_repository),
    idem_repo: IdempotencyRepository = Depends(get_idempotency_repository),
    audit_repo: AuditRepository = Depends(get_audit_repository),
    actor_id: str = Depends(_actor_id),
):
    return _mutation_endpoint(
        event_id,
        idempotency_key,
        if_match,
        repo,
        idem_repo,
        audit_repo,
        actor_id,
        "publish",
        publish_event,
    )


@router.post("/{event_id}/pause")
def pause(
    event_id: str,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    if_match: str = Header(alias="If-Match"),
    repo: EventRepository = Depends(get_repository),
    idem_repo: IdempotencyRepository = Depends(get_idempotency_repository),
    audit_repo: AuditRepository = Depends(get_audit_repository),
    actor_id: str = Depends(_actor_id),
):
    return _mutation_endpoint(
        event_id,
        idempotency_key,
        if_match,
        repo,
        idem_repo,
        audit_repo,
        actor_id,
        "pause",
        pause_event,
    )


@router.post("/{event_id}/cancel")
def cancel(
    event_id: str,
    reason: str = Query(default=""),
    idempotency_key: str = Header(alias="Idempotency-Key"),
    if_match: str = Header(alias="If-Match"),
    repo: EventRepository = Depends(get_repository),
    idem_repo: IdempotencyRepository = Depends(get_idempotency_repository),
    audit_repo: AuditRepository = Depends(get_audit_repository),
    actor_id: str = Depends(_actor_id),
):
    expected_version = _parse_if_match(if_match)
    scope = f"cancel:{event_id}:{idempotency_key}"

    def execute() -> tuple[int, dict]:
        event = cancel_event(
            repo, audit_repo, actor_id, event_id, expected_version, reason
        )
        return 200, jsonable_encoder(EventResponse.from_entity(event))

    status_code, body = run_idempotent(
        idem_repo,
        scope,
        {"eventId": event_id, "ifMatch": expected_version, "reason": reason},
        execute,
    )
    return JSONResponse(status_code=status_code, content=body)


@router.get("/{event_id}/sale-eligibility")
def sale_eligibility(event_id: str, repo: EventRepository = Depends(get_repository)):
    result = get_sale_eligibility(repo, event_id)
    event = result["event"]
    response = SaleEligibilityResponse(
        eventId=event.id,
        eligible=result["eligible"],
        status=event.status.value,
        reasonCode=result["reasonCode"],
        priceSnapshot=[
            TicketTypeResponse(
                code=t.code,
                name=t.name,
                price=MoneyResponse(
                    amountMinor=t.price.amount_minor, currency=t.price.currency
                ),
            )
            for t in event.ticket_types
        ],
    )
    return jsonable_encoder(response)
