from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, Body, Header, Query, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import TypeAdapter

from app.api.schemas import (
    AdminSeatInventoryProjection,
    AggregateHealth,
    BookingListProjection,
    BookingResult,
    BookingStatus,
    CancelBookingRequest,
    CheckInRequest,
    CheckInResult,
    CheckInValidateRequest,
    ConfigureSeatInventoryRequest,
    ConfigureSeatInventoryResult,
    ConsentUpdateRequest,
    ConsentUpdateResult,
    CustomerProfileInput,
    CustomerProfileProjection,
    ErrorResponse,
    EventAdminRequest,
    HealthStatus,
    LoginRequest,
    PlaceBookingRequest,
    RegisterRequest,
    PublicEvent,
    SeatMapProjection,
    TicketListProjection,
    TicketProjection,
    TicketValidationResult,
    TokenResponse,
    TraceStep,
    User,
    WsTicketRequest,
    WsTicketResponse,
)
from app.application.projections import (
    booking_projection,
    event_projection,
    event_request_to_provider,
)
from app.domain.errors import EsbError
from app.domain.models import Principal, RequestContext

router = APIRouter()

ETAG_HEADER = {
    "ETag": {
        "description": "Strong resource-version validator used by If-Match.",
        "schema": {"type": "string", "pattern": '^"[1-9][0-9]*"$'},
    }
}
LOCATION_RETRY_HEADERS = {
    "Location": {"schema": {"type": "string"}},
    "Retry-After": {"schema": {"type": "string", "pattern": r"^[1-9][0-9]*$"}},
}
AUTH_SESSION_HEADERS = {
    "Set-Cookie": {
        "description": (
            "Identity refresh and CSRF cookies. Multiple Set-Cookie header fields may be returned; "
            "the ESB preserves HttpOnly, Secure and SameSite attributes and rewrites Path to /api/auth."
        ),
        "schema": {"type": "string"},
    },
    "Cache-Control": {
        "description": "Authentication responses are not cacheable.",
        "schema": {"type": "string", "example": "no-store"},
    },
    "Pragma": {
        "description": "Legacy no-cache directive preserved from Identity.",
        "schema": {"type": "string", "example": "no-cache"},
    },
}
COMMON_ERRORS = {
    400: {"model": ErrorResponse, "description": "Malformed request."},
    401: {"model": ErrorResponse, "description": "Authentication failed."},
    402: {"model": ErrorResponse, "description": "Payment was declined."},
    403: {"model": ErrorResponse, "description": "Not authorized."},
    404: {"model": ErrorResponse, "description": "Resource not found."},
    409: {"model": ErrorResponse, "description": "State, uniqueness or idempotency conflict."},
    412: {"model": ErrorResponse, "description": "If-Match does not match the resource version."},
    413: {"model": ErrorResponse, "description": "Request payload is too large."},
    423: {"model": ErrorResponse, "description": "Identity account is temporarily locked."},
    422: {"model": ErrorResponse, "description": "Validation or domain-rule rejection."},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded."},
    502: {"model": ErrorResponse, "description": "Provider returned an invalid response."},
    503: {"model": ErrorResponse, "description": "Required dependency is unavailable."},
    500: {"model": ErrorResponse, "description": "Unexpected gateway failure."},
    504: {"model": ErrorResponse, "description": "Request deadline exceeded."},
}


def response_docs(*statuses: int, etag_statuses: tuple[int, ...] = ()) -> dict[int, dict[str, Any]]:
    # FastAPI automatically documents request validation as 422. The runtime handler
    # returns the canonical ErrorResponse, so every operation must advertise that same
    # envelope instead of FastAPI's default HTTPValidationError.
    requested = {*statuses, 422}
    docs = {status: dict(value) for status, value in COMMON_ERRORS.items() if status in requested}
    for status in etag_statuses:
        docs.setdefault(status, {})["headers"] = ETAG_HEADER
    return docs


async def request_context(request: Request, *, optional_auth: bool = False) -> RequestContext:
    authorization = request.headers.get("Authorization")
    if optional_auth and not authorization:
        principal = Principal("anonymous")
    else:
        principal = await request.app.state.container.auth.verify(authorization)
    return RequestContext(
        request.state.correlation_id,
        request.state.trace_id,
        request.state.deadline,
        principal,
    )


def parse_if_match(value: str) -> int:
    stripped = value.strip()
    if (
        len(stripped) < 3
        or stripped[0] != '"'
        or stripped[-1] != '"'
        or not stripped[1:-1].isdigit()
        or stripped[1] == "0"
    ):
        raise EsbError(
            "INVALID_IF_MATCH",
            'If-Match must contain a quoted positive resource version such as "3"',
            400,
        )
    return int(stripped[1:-1])


def _ticket_validation_key(subject: str, qr_token: str) -> str:
    digest = hashlib.sha256(f"{subject}:{qr_token}".encode("utf-8")).hexdigest()
    return f"validate-{digest[:48]}"


def _resource_version(payload: dict[str, Any]) -> int | None:
    value: Any = payload.get("resourceVersion")
    if value is None and isinstance(payload.get("ticket"), dict):
        value = payload["ticket"].get("resourceVersion")
    try:
        parsed = int(value)
        return parsed if parsed > 0 else None
    except (TypeError, ValueError):
        return None


def _validated_payload(model: Any, payload: Any) -> Any:
    adapter = TypeAdapter(model)
    value = adapter.validate_python(payload)
    return adapter.dump_python(value, mode="json", by_alias=True)


def json_response(
    model: Any,
    payload: Any,
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    content = _validated_payload(model, payload)
    response = JSONResponse(content, status_code=status_code)
    if isinstance(content, dict):
        version = _resource_version(content)
        if version is not None:
            response.headers["ETag"] = f'"{version}"'
    for name, value in (headers or {}).items():
        response.headers[name] = value
    return response


def _identity_context(request: Request) -> RequestContext:
    return RequestContext(
        request.state.correlation_id,
        request.state.trace_id,
        request.state.deadline,
        Principal("anonymous"),
    )


def _identity_headers(request: Request, *names: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for name in names:
        value = request.headers.get(name)
        if value:
            values[name] = value
    return values


def _identity_response(
    provider,
    *,
    success_model: Any | None = None,
) -> Response:
    content = provider.content
    if provider.status_code >= 400:
        try:
            payload = json.loads(content.decode("utf-8"))
            validated = _validated_payload(ErrorResponse, payload)
            content = json.dumps(validated, separators=(",", ":")).encode("utf-8")
        except (UnicodeDecodeError, ValueError, TypeError):
            raise EsbError(
                "IDENTITY_PROTOCOL_ERROR",
                "Identity Service returned an invalid error response",
                502,
                True,
            )
    elif success_model is not None and provider.status_code != 204:
        try:
            payload = json.loads(content.decode("utf-8"))
            validated = _validated_payload(success_model, payload)
            content = json.dumps(validated, separators=(",", ":")).encode("utf-8")
        except (UnicodeDecodeError, ValueError, TypeError) as exc:
            raise EsbError(
                "IDENTITY_PROTOCOL_ERROR",
                "Identity Service returned a response that violates its contract",
                502,
                True,
            ) from exc

    response = Response(
        content=content if provider.status_code != 204 else b"",
        status_code=provider.status_code,
        media_type=None if provider.status_code == 204 else provider.media_type,
    )
    for name, value in provider.headers:
        if name.casefold() not in {"x-correlation-id", "x-trace-id"}:
            response.headers.append(name, value)
    for cookie in provider.set_cookies:
        response.raw_headers.append((b"set-cookie", cookie.encode("latin-1")))
    return response


def customer_projection(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "customerId": str(value.get("customerId") or value.get("id") or ""),
        "fullName": value.get("name") or value.get("fullName"),
        "email": value.get("email"),
        "phone": value.get("phone"),
        "status": value.get("status", "ACTIVE"),
        "resourceVersion": value.get("resourceVersion"),
        "createdAt": value.get("createdAt"),
        "updatedAt": value.get("updatedAt"),
    }


async def _mapped_customer(request: Request, ctx: RequestContext) -> tuple[str, dict[str, Any]]:
    mapping = await request.app.state.container.customer.resolve_identity(
        ctx.principal.subject, ctx
    )
    customer_id = str(mapping.get("customerId") or mapping.get("id") or "")
    if not customer_id:
        raise EsbError(
            "IDENTITY_NOT_MAPPED",
            "Authenticated identity has no active Customer mapping",
            404,
        )
    customer = await request.app.state.container.customer.get(customer_id, ctx)
    return customer_id, customer


@router.post(
    "/api/auth/register",
    operation_id="registerIdentityAccountViaEsb",
    status_code=201,
    response_model=User,
    responses=response_docs(400, 409, 413, 422, 500, 502, 503, 504),
)
async def auth_register(
    body: RegisterRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
):
    provider = await request.app.state.container.identity.proxy(
        "POST",
        "/auth/register",
        _identity_context(request),
        body=body.model_dump_json().encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Idempotency-Key": idempotency_key,
        },
        idempotent=True,
    )
    return _identity_response(provider, success_model=User)


@router.post(
    "/api/auth/login",
    operation_id="loginIdentityAccountViaEsb",
    response_model=TokenResponse,
    responses={
        200: {"headers": AUTH_SESSION_HEADERS},
        **response_docs(401, 403, 422, 423, 429, 500, 502, 503, 504),
    },
)
async def auth_login(body: LoginRequest, request: Request):
    provider = await request.app.state.container.identity.proxy(
        "POST",
        "/auth/login",
        _identity_context(request),
        body=body.model_dump_json().encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    return _identity_response(provider, success_model=TokenResponse)


@router.post(
    "/api/auth/refresh",
    operation_id="refreshIdentitySessionViaEsb",
    response_model=TokenResponse,
    responses={
        200: {"headers": AUTH_SESSION_HEADERS},
        **response_docs(401, 403, 500, 502, 503, 504),
    },
)
async def auth_refresh(request: Request):
    provider = await request.app.state.container.identity.proxy(
        "POST",
        "/auth/refresh",
        _identity_context(request),
        headers=_identity_headers(request, "Cookie", "X-CSRF-Token"),
    )
    return _identity_response(provider, success_model=TokenResponse)


@router.post(
    "/api/auth/logout",
    operation_id="logoutIdentitySessionViaEsb",
    status_code=204,
    response_class=Response,
    responses={
        204: {"headers": AUTH_SESSION_HEADERS},
        **response_docs(403, 500, 502, 503, 504),
    },
)
async def auth_logout(request: Request):
    provider = await request.app.state.container.identity.proxy(
        "POST",
        "/auth/logout",
        _identity_context(request),
        headers=_identity_headers(request, "Cookie", "X-CSRF-Token"),
    )
    return _identity_response(provider)


@router.get(
    "/api/auth/me",
    operation_id="getCurrentIdentityPrincipalViaEsb",
    response_model=User,
    responses=response_docs(401, 403, 500, 502, 503, 504),
)
async def auth_me(request: Request):
    provider = await request.app.state.container.identity.proxy(
        "GET",
        "/auth/me",
        _identity_context(request),
        headers=_identity_headers(request, "Authorization"),
        idempotent=True,
    )
    return _identity_response(provider, success_model=User)


@router.get(
    "/api/events",
    operation_id="publicListEvents",
    response_model=list[PublicEvent],
    responses=response_docs(502, 503, 504),
)
async def list_events(request: Request):
    context = await request_context(request, optional_auth=True)
    payload = await request.app.state.container.queries.event_list(
        dict(request.query_params), context
    )
    return json_response(list[PublicEvent], payload)


@router.get(
    "/api/events/{eventId}",
    operation_id="publicGetEvent",
    response_model=PublicEvent,
    responses={**response_docs(404, 502, 503, 504), 200: {"headers": ETAG_HEADER}},
)
async def get_event(eventId: str, request: Request):
    context = await request_context(request, optional_auth=True)
    payload = await request.app.state.container.queries.event_get(eventId, context)
    return json_response(PublicEvent, payload)


@router.get(
    "/api/events/{eventId}/seat-map",
    operation_id="publicGetEventSeatMap",
    response_model=SeatMapProjection,
    responses=response_docs(404, 502, 503, 504),
)
async def seat_map(eventId: str, request: Request):
    payload = await request.app.state.container.queries.seat_map(
        eventId, await request_context(request, optional_auth=True)
    )
    return json_response(SeatMapProjection, payload)


@router.post(
    "/api/bookings",
    operation_id="placeBooking",
    status_code=201,
    response_model=BookingResult,
    responses={
        201: {"headers": ETAG_HEADER},
        202: {
            "model": BookingResult,
            "description": "Booking is reconciling.",
            "headers": {**ETAG_HEADER, **LOCATION_RETRY_HEADERS},
        },
        **response_docs(400, 401, 402, 409, 422, 502, 503, 504),
    },
)
async def place_booking(
    body: PlaceBookingRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
):
    status, payload = await request.app.state.container.booking_saga.place(
        body.model_dump(exclude_none=True),
        idempotency_key,
        await request_context(request),
    )
    headers: dict[str, str] = {}
    if status == 202:
        if payload.get("bookingId"):
            headers["Location"] = f"/api/bookings/{payload['bookingId']}"
        headers["Retry-After"] = "2"
    return json_response(BookingResult, payload, status_code=status, headers=headers)


@router.get(
    "/api/bookings",
    operation_id="publicListBookings",
    response_model=BookingListProjection,
    responses=response_docs(401, 403, 502, 503, 504),
)
async def list_bookings(
    request: Request,
    status: BookingStatus | None = None,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
):
    payload = await request.app.state.container.queries.booking_list(
        {"status": status, "page": page, "pageSize": pageSize},
        await request_context(request),
    )
    return json_response(BookingListProjection, payload)


@router.get(
    "/api/bookings/{bookingId}",
    operation_id="publicGetBooking",
    response_model=BookingResult,
    responses={**response_docs(401, 403, 404, 502, 503, 504), 200: {"headers": ETAG_HEADER}},
)
async def get_booking(bookingId: str, request: Request):
    payload = await request.app.state.container.queries.booking_get(
        bookingId, await request_context(request)
    )
    return json_response(BookingResult, payload)


@router.post(
    "/api/bookings/{bookingId}/cancel",
    operation_id="publicCancelBooking",
    response_model=BookingResult,
    responses={**response_docs(400, 401, 403, 404, 409, 412, 422, 502, 503, 504), 200: {"headers": ETAG_HEADER}},
)
async def cancel_booking(
    bookingId: str,
    request: Request,
    body: CancelBookingRequest = Body(default_factory=CancelBookingRequest),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    if_match: str = Header(alias="If-Match"),
):
    context = await request_context(request)
    payload = body.model_dump()
    payload["expectedVersion"] = parse_if_match(if_match)
    result = await request.app.state.container.cancellation.cancel(
        bookingId, payload, idempotency_key, context
    )
    return json_response(BookingResult, booking_projection(result, context))


@router.get(
    "/api/bookings/{bookingId}/tickets",
    operation_id="publicListBookingTickets",
    response_model=list[TicketProjection],
    responses=response_docs(401, 403, 404, 502, 503, 504),
)
async def booking_tickets(bookingId: str, request: Request):
    payload = await request.app.state.container.queries.booking_tickets(
        bookingId, await request_context(request)
    )
    return json_response(list[TicketProjection], payload)


@router.get(
    "/api/tickets",
    operation_id="publicListTickets",
    response_model=TicketListProjection,
    responses=response_docs(401, 403, 502, 503, 504),
)
async def tickets(
    request: Request,
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
):
    payload = await request.app.state.container.queries.ticket_list(
        await request_context(request), page=page, page_size=pageSize
    )
    return json_response(TicketListProjection, payload)


@router.get(
    "/api/tickets/{ticketId}",
    operation_id="publicGetTicket",
    response_model=TicketProjection,
    responses={**response_docs(401, 403, 404, 502, 503, 504), 200: {"headers": ETAG_HEADER}},
)
async def ticket(ticketId: str, request: Request):
    payload = await request.app.state.container.queries.ticket_get(
        ticketId, await request_context(request)
    )
    return json_response(TicketProjection, payload)


@router.get(
    "/api/me/customer",
    operation_id="getMyCustomerProfile",
    response_model=CustomerProfileProjection,
    responses={**response_docs(401, 404, 502, 503, 504), 200: {"headers": ETAG_HEADER}},
)
async def get_my_customer(request: Request):
    ctx = await request_context(request)
    _, customer = await _mapped_customer(request, ctx)
    return json_response(CustomerProfileProjection, customer_projection(customer))


@router.put(
    "/api/me/customer",
    operation_id="upsertMyCustomerProfile",
    response_model=CustomerProfileProjection,
    responses={
        200: {"headers": ETAG_HEADER},
        201: {"model": CustomerProfileProjection, "headers": ETAG_HEADER},
        **response_docs(400, 401, 409, 412, 422, 502, 503, 504),
    },
)
async def upsert_my_customer(
    body: CustomerProfileInput,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    ctx = await request_context(request)
    provider_payload = {
        "name": body.fullName,
        "email": str(body.email),
        "phone": body.phone,
    }
    try:
        customer_id, current = await _mapped_customer(request, ctx)
    except EsbError as exc:
        if exc.status_code != 404 and exc.code not in {"IDENTITY_NOT_MAPPED", "CUSTOMER_NOT_FOUND"}:
            raise
        created = await request.app.state.container.customer.create(
            provider_payload, idempotency_key + ":customer", ctx
        )
        customer_id = str(created.get("customerId") or created.get("id") or "")
        if not customer_id:
            raise EsbError(
                "CUSTOMER_PROTOCOL_ERROR",
                "Customer Service did not return customerId",
                502,
                True,
            )
        created_version = int(created.get("resourceVersion") or 1)
        await request.app.state.container.customer.link_identity(
            customer_id,
            ctx.principal.subject,
            idempotency_key + ":identity-link",
            f'"{created_version}"',
            ctx,
        )
        return json_response(
            CustomerProfileProjection,
            customer_projection(created),
            status_code=201,
        )

    version_header = if_match or f'"{int(current["resourceVersion"])}"'
    if if_match is not None:
        parse_if_match(if_match)
    updated = await request.app.state.container.customer.replace(
        customer_id,
        provider_payload,
        idempotency_key + ":customer-update",
        version_header,
        ctx,
    )
    return json_response(CustomerProfileProjection, customer_projection(updated))


@router.post(
    "/api/me/customer/consents",
    operation_id="updateMyCustomerConsent",
    response_model=ConsentUpdateResult,
    responses={**response_docs(400, 401, 404, 409, 412, 422, 502, 503, 504), 200: {"headers": ETAG_HEADER}},
)
async def update_my_customer_consent(
    body: ConsentUpdateRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    ctx = await request_context(request)
    customer_id, current = await _mapped_customer(request, ctx)
    version_header = if_match or f'"{int(current["resourceVersion"])}"'
    if if_match is not None:
        parse_if_match(if_match)
    await request.app.state.container.customer.update_consent(
        customer_id,
        body.model_dump(),
        idempotency_key,
        version_header,
        ctx,
    )
    # Customer Service returns 204 for the command. Re-read the aggregate rather than
    # inventing the next resource version inside the ESB.
    authoritative = await request.app.state.container.customer.get(customer_id, ctx)
    result = {
        "customerId": customer_id,
        "channel": body.channel,
        "granted": body.granted,
        "resourceVersion": authoritative.get("resourceVersion"),
    }
    return json_response(ConsentUpdateResult, result)


async def admin_context(request: Request) -> RequestContext:
    context = await request_context(request)
    context.principal.require_any("ADMIN")
    return context


@router.post(
    "/api/admin/events",
    operation_id="adminCreateEvent",
    status_code=201,
    response_model=PublicEvent,
    responses={201: {"headers": ETAG_HEADER}, **response_docs(400, 401, 403, 409, 422, 502, 503, 504)},
)
async def admin_create_event(
    body: EventAdminRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
):
    context = await admin_context(request)
    raw = await request.app.state.container.event.admin_command(
        "create",
        None,
        event_request_to_provider(body.model_dump(exclude_none=True)),
        {"Idempotency-Key": idempotency_key},
        context,
    )
    return json_response(PublicEvent, event_projection(raw), status_code=201)


@router.put(
    "/api/admin/events/{eventId}",
    operation_id="adminReplaceEvent",
    response_model=PublicEvent,
    responses={**response_docs(400, 401, 403, 404, 409, 412, 422, 502, 503, 504), 200: {"headers": ETAG_HEADER}},
)
async def admin_replace_event(
    eventId: str,
    body: EventAdminRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    if_match: str = Header(alias="If-Match"),
):
    parse_if_match(if_match)
    context = await admin_context(request)
    raw = await request.app.state.container.event.admin_command(
        "replace",
        eventId,
        event_request_to_provider(body.model_dump(exclude_none=True)),
        {"Idempotency-Key": idempotency_key, "If-Match": if_match},
        context,
    )
    return json_response(PublicEvent, event_projection(raw))


async def event_state_command(
    action: str,
    eventId: str,
    request: Request,
    idempotency_key: str,
    if_match: str,
):
    parse_if_match(if_match)
    context = await admin_context(request)
    raw = await request.app.state.container.event.admin_command(
        action,
        eventId,
        {},
        {"Idempotency-Key": idempotency_key, "If-Match": if_match},
        context,
    )
    return json_response(PublicEvent, event_projection(raw))


_EVENT_COMMAND_RESPONSES = {
    **response_docs(400, 401, 403, 404, 409, 412, 422, 502, 503, 504),
    200: {"headers": ETAG_HEADER},
}


@router.post("/api/admin/events/{eventId}/publish", operation_id="adminPublishEvent", response_model=PublicEvent, responses=_EVENT_COMMAND_RESPONSES)
async def admin_publish_event(eventId: str, request: Request, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128), if_match: str = Header(alias="If-Match")):
    return await event_state_command("publish", eventId, request, idempotency_key, if_match)


@router.post("/api/admin/events/{eventId}/pause", operation_id="adminPauseEvent", response_model=PublicEvent, responses=_EVENT_COMMAND_RESPONSES)
async def admin_pause_event(eventId: str, request: Request, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128), if_match: str = Header(alias="If-Match")):
    return await event_state_command("pause", eventId, request, idempotency_key, if_match)


@router.post("/api/admin/events/{eventId}/close", operation_id="adminCloseEvent", response_model=PublicEvent, responses=_EVENT_COMMAND_RESPONSES)
async def admin_close_event(eventId: str, request: Request, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128), if_match: str = Header(alias="If-Match")):
    return await event_state_command("close", eventId, request, idempotency_key, if_match)


@router.post("/api/admin/events/{eventId}/cancel", operation_id="adminCancelEvent", response_model=PublicEvent, responses=_EVENT_COMMAND_RESPONSES)
async def admin_cancel_event(eventId: str, request: Request, idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128), if_match: str = Header(alias="If-Match")):
    return await event_state_command("cancel", eventId, request, idempotency_key, if_match)


@router.get(
    "/api/admin/events/{eventId}/seat-inventory",
    operation_id="adminGetSeatInventory",
    response_model=AdminSeatInventoryProjection,
    responses=response_docs(401, 403, 404, 502, 503, 504),
)
async def admin_get_seat_inventory(eventId: str, request: Request):
    await admin_context(request)
    payload = await request.app.state.container.queries.seat_map(
        eventId, await request_context(request)
    )
    return json_response(AdminSeatInventoryProjection, payload)


@router.put(
    "/api/admin/events/{eventId}/seat-inventory",
    operation_id="adminConfigureSeatInventory",
    response_model=ConfigureSeatInventoryResult,
    responses=response_docs(400, 401, 403, 404, 409, 422, 502, 503, 504),
)
async def admin_configure_seat_inventory(
    eventId: str,
    body: ConfigureSeatInventoryRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
):
    context = await admin_context(request)
    result = await request.app.state.container.seat.configure_inventory(
        eventId,
        body.inventoryVersion,
        [
            {
                "seatId": seat.seatId,
                "section": seat.section,
                "rowLabel": seat.rowLabel,
                "seatNumber": seat.seatNumber,
                "ticketTypeCode": seat.ticketTypeId,
                "status": seat.status,
            }
            for seat in body.seats
        ],
        idempotency_key,
        context,
    )
    return json_response(ConfigureSeatInventoryResult, result)


@router.post(
    "/api/check-in/validate",
    operation_id="validateTicketForCheckIn",
    response_model=TicketValidationResult,
    responses={**response_docs(400, 401, 403, 409, 422, 429, 502, 503, 504), 200: {"headers": ETAG_HEADER}},
)
async def validate_ticket(body: CheckInValidateRequest, request: Request):
    context = await request_context(request)
    context.principal.require_any("CHECKIN_STAFF", "ADMIN")
    await request.app.state.container.limiter.check(
        "checkin:" + context.principal.subject,
        request.app.state.settings.checkin_rate_limit,
        request.app.state.settings.rate_limit_window_seconds,
    )
    try:
        raw = await request.app.state.container.ticket.validate(
            body.model_dump(),
            _ticket_validation_key(context.principal.subject, body.qrToken),
            context,
        )
    except EsbError as exc:
        if exc.status_code in {404, 409}:
            return json_response(
                TicketValidationResult,
                {
                    "valid": False,
                    "ticket": None,
                    "code": exc.code,
                    "message": exc.message,
                    "correlationId": context.correlation_id,
                },
            )
        raise
    ticket_view = await request.app.state.container.queries.staff_ticket_projection(
        raw, context, include_qr=False
    )
    return json_response(
        TicketValidationResult,
        {
            "valid": True,
            "ticket": ticket_view,
            "code": None,
            "message": None,
            "correlationId": context.correlation_id,
        },
    )


@router.post(
    "/api/check-in/tickets/{ticketId}",
    operation_id="checkInTicket",
    response_model=CheckInResult,
    responses={**response_docs(400, 401, 403, 404, 409, 412, 422, 429, 502, 503, 504), 200: {"headers": ETAG_HEADER}},
)
async def checkin(
    ticketId: str,
    body: CheckInRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    if_match: str = Header(alias="If-Match"),
):
    context = await request_context(request)
    context.principal.require_any("CHECKIN_STAFF", "ADMIN")
    await request.app.state.container.limiter.check(
        "checkin:" + context.principal.subject,
        request.app.state.settings.checkin_rate_limit,
        request.app.state.settings.rate_limit_window_seconds,
    )
    validated = await request.app.state.container.ticket.validate(
        {"qrToken": body.qrToken},
        _ticket_validation_key(context.principal.subject, body.qrToken),
        context,
    )
    validated_ticket_id = str(validated.get("ticketId") or validated.get("id") or "")
    if validated_ticket_id != ticketId:
        raise EsbError(
            "QR_TICKET_MISMATCH",
            "The QR token does not belong to the requested ticket",
            409,
            False,
        )
    expected_version = parse_if_match(if_match)
    provider_version = validated.get("resourceVersion")
    if provider_version is not None and int(provider_version) != expected_version:
        raise EsbError(
            "PRECONDITION_FAILED",
            "The ticket version changed after validation",
            412,
            True,
        )
    raw = await request.app.state.container.ticket.check_in(
        ticketId,
        {},
        {"Idempotency-Key": idempotency_key, "If-Match": if_match},
        context,
    )
    ticket_view = await request.app.state.container.queries.staff_ticket_projection(
        raw, context, include_qr=False
    )
    return json_response(
        CheckInResult,
        {"ticket": ticket_view, "correlationId": context.correlation_id},
    )


@router.post(
    "/api/realtime/ws-tickets",
    operation_id="issueRealtimeWebSocketTicket",
    status_code=201,
    response_model=WsTicketResponse,
    responses=response_docs(400, 401, 403, 404, 409, 422, 429, 502, 503, 504),
)
async def realtime_ticket(
    body: WsTicketRequest,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
):
    context = await request_context(request)
    await request.app.state.container.queries.booking_get(body.bookingId, context)
    await request.app.state.container.limiter.check(
        "ws:" + context.principal.subject,
        request.app.state.settings.realtime_ticket_rate_limit,
        request.app.state.settings.rate_limit_window_seconds,
    )
    payload = await request.app.state.container.ws_ticket_issuer.issue(
        body.bookingId, context.principal.subject, idempotency_key
    )
    return json_response(WsTicketResponse, payload, status_code=201)


@router.get(
    "/api/traces/{correlationId}",
    operation_id="getWorkflowTrace",
    response_model=list[TraceStep],
    responses=response_docs(401, 403, 404, 503, 504),
)
async def trace(correlationId: str, request: Request):
    context = await request_context(request)
    context.principal.require_any("ADMIN")
    workflow = await request.app.state.container.workflows.find_by_correlation(correlationId)
    if not workflow:
        raise EsbError("TRACE_NOT_FOUND", "Workflow trace was not found", 404)
    payload = workflow.evidence.get(
        "traceSteps",
        [
            {
                "service": "booking-orchestrator",
                "operation": "booking-workflow",
                "status": workflow.status.value,
                "durationMs": 0,
                "errorCode": None,
            }
        ],
    )
    return json_response(list[TraceStep], payload)


@router.get(
    "/api/health",
    operation_id="aggregateHealth",
    response_model=AggregateHealth,
    responses={503: {"model": AggregateHealth, "description": "One or more critical dependencies are unavailable."}},
)
async def health(request: Request):
    status, payload = await request.app.state.container.health.check()
    return json_response(AggregateHealth, payload, status_code=status)


@router.get("/health/live", operation_id="esbLiveness", response_model=HealthStatus)
async def live():
    return json_response(
        HealthStatus,
        {"status": "UP", "service": "booking-orchestrator", "version": "2.2.0"},
    )


@router.get(
    "/health/ready",
    operation_id="esbReadiness",
    response_model=HealthStatus,
    responses={503: {"model": HealthStatus, "description": "Service is not ready."}},
)
async def ready(request: Request):
    status, payload = await request.app.state.container.health.ready()
    return json_response(HealthStatus, payload, status_code=status)


@router.get("/metrics", include_in_schema=False)
async def metrics(request: Request):
    return PlainTextResponse(
        request.app.state.metrics.render(), media_type="text/plain; version=0.0.4"
    )
