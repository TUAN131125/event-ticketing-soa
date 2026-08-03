from __future__ import annotations

from typing import Annotated, Any, cast

from fastapi import APIRouter, Header, HTTPException, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.schemas import (
    BookingResult,
    ErrorResponse,
    PlaceBookingRequest,
    PublicEvent,
    TraceStep,
    WsTicketRequest,
    WsTicketResponse,
)
from app.domain.errors import AccessDenied, DependencyFailure
from app.domain.models import PlaceBookingCommand, Principal, RequestContext

bearer = HTTPBearer(auto_error=False, scheme_name="bearerAuth")
browser_bearer = HTTPBearer(auto_error=False, scheme_name="BrowserBearerAuth")


async def _principal(request: Request, credentials: HTTPAuthorizationCredentials | None) -> Principal:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return cast(
        Principal,
        await request.app.state.container.browser_auth.verify(credentials.credentials),
    )


async def bearer_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)],
) -> Principal:
    return await _principal(request, credentials)


async def browser_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(browser_bearer)],
) -> Principal:
    return await _principal(request, credentials)


def context(request: Request, principal: Principal) -> RequestContext:
    return RequestContext(
        request.state.correlation_id,
        request.headers.get("traceparent"),
        request.state.deadline,
        principal,
    )


def create_router() -> APIRouter:
    router = APIRouter()

    def errors(*codes: int) -> dict[int | str, dict[str, Any]]:
        return {code: {"model": ErrorResponse} for code in codes}

    @router.get("/api/events", operation_id="publicListEvents", response_model=list[PublicEvent])
    async def list_events(request: Request) -> Any:
        return await request.app.state.container.queries.list_events(context(request, Principal("anonymous", ())))

    @router.get(
        "/api/events/{eventId}",
        operation_id="publicGetEvent",
        response_model=PublicEvent,
        responses=errors(404, 503),
    )
    async def get_event(eventId: str, request: Request) -> Any:
        return await request.app.state.container.queries.get_event(eventId, context(request, Principal("anonymous", ())))

    @router.post(
        "/api/bookings",
        operation_id="placeBooking",
        response_model=BookingResult,
        status_code=201,
        responses={202: {"model": BookingResult}, **errors(402, 409, 422, 503)},
    )
    async def place_booking(
        payload: PlaceBookingRequest,
        request: Request,
        principal: Annotated[Principal, Security(bearer_principal)],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
        correlation_id: Annotated[str | None, Header(alias="X-Correlation-ID", min_length=16, max_length=64)] = None,
        traceparent: Annotated[str | None, Header()] = None,
    ) -> Any:
        command = PlaceBookingCommand(
            payload.customerId,
            payload.eventId,
            tuple(payload.seatIds),
            payload.paymentMethodToken,
            idempotency_key,
        )
        result = await request.app.state.container.booking_saga.execute(command, context(request, principal))
        return JSONResponse(dict(result.body), status_code=result.status_code)

    @router.get(
        "/api/bookings/{bookingId}",
        operation_id="publicGetBooking",
        response_model=BookingResult,
        responses=errors(403, 404),
    )
    async def get_booking(
        bookingId: str,
        request: Request,
        principal: Annotated[Principal, Security(bearer_principal)],
    ) -> Any:
        return await request.app.state.container.queries.get_booking(bookingId, context(request, principal))

    @router.post(
        "/api/bookings/{bookingId}/cancel",
        operation_id="publicCancelBooking",
        response_model=BookingResult,
        responses=errors(403, 404, 409, 503),
    )
    async def cancel_booking(
        bookingId: str,
        request: Request,
        principal: Annotated[Principal, Security(bearer_principal)],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
    ) -> Any:
        result = await request.app.state.container.cancellation_saga.execute(bookingId, idempotency_key, context(request, principal))
        return JSONResponse(dict(result.body), status_code=result.status_code)

    @router.get("/api/health", operation_id="aggregateHealth", responses=errors(503))
    async def health(request: Request) -> dict[str, str]:
        if request.app.state.container.database is not None:
            try:
                await request.app.state.container.database.ping()
            except Exception as exc:  # noqa: BLE001 -- health normalizes database driver failures
                raise DependencyFailure("DEPENDENCY_UNAVAILABLE", "Workflow persistence is unavailable.", 503, True) from exc
        return {"status": "UP"}

    @router.get(
        "/api/traces/{correlationId}",
        operation_id="getWorkflowTrace",
        response_model=list[TraceStep],
        responses=errors(403, 404),
    )
    async def trace(
        correlationId: str,
        request: Request,
        principal: Annotated[Principal, Security(bearer_principal)],
    ) -> Any:
        return await request.app.state.container.queries.trace(correlationId, context(request, principal))

    @router.post(
        "/api/realtime/ws-tickets",
        operation_id="issueRealtimeWebSocketTicket",
        response_model=WsTicketResponse,
        status_code=201,
        responses=errors(400, 401, 403, 429, 503),
    )
    async def issue_ws_ticket(
        payload: WsTicketRequest,
        request: Request,
        principal: Annotated[Principal, Security(browser_principal)],
        correlation_id: Annotated[str, Header(alias="X-Correlation-ID", min_length=16, max_length=64)],
    ) -> Any:
        ctx = RequestContext(
            correlation_id,
            request.headers.get("traceparent"),
            request.state.deadline,
            principal,
        )
        decision = await request.app.state.container.bookings.decide_access(payload.bookingId, ctx)
        if not decision.get("allowed"):
            raise AccessDenied()
        ticket, expires = request.app.state.container.ws_tickets.issue(principal.subject, payload.bookingId)
        return {"ticket": ticket, "bookingId": payload.bookingId, "expiresAt": expires}

    return router
