from __future__ import annotations

from typing import Annotated, Any, cast

from fastapi import APIRouter, Header, HTTPException, Request, Response, Security
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.schemas import (
    AggregateHealthStatus,
    BookingResult,
    DependencyHealthStatus,
    ErrorResponse,
    PlaceBookingRequest,
    PublicEvent,
    TraceStep,
    WsTicketRequest,
    WsTicketResponse,
)
from app.domain.errors import AccessDenied, DependencyFailure
from app.domain.models import PlaceBookingCommand, Principal, RequestContext

bearer = HTTPBearer(auto_error=False, scheme_name="UserJwt")

# The canonical public contract declares both trace headers as optional on every
# operation. They are consumed by the ingress middleware; declaring them here keeps the
# generated OpenAPI identical to contracts/esb-public-api.yaml.
CorrelationHeader = Annotated[str | None, Header(alias="X-Correlation-ID", min_length=16, max_length=64)]
TraceparentHeader = Annotated[str | None, Header(alias="traceparent")]


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
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer)],
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

    @router.get(
        "/api/events",
        operation_id="publicListEvents",
        response_model=list[PublicEvent],
        responses=errors(500),
    )
    async def list_events(
        request: Request,
        correlation_id: CorrelationHeader = None,
        traceparent: TraceparentHeader = None,
    ) -> Any:
        body = await request.app.state.container.queries.list_events(context(request, Principal("anonymous", ())))
        return JSONResponse(jsonable_encoder(body), headers={"ETag": '"1"'})

    @router.get(
        "/api/events/{eventId}",
        operation_id="publicGetEvent",
        response_model=PublicEvent,
        responses=errors(404, 503),
    )
    async def get_event(
        eventId: str,
        request: Request,
        correlation_id: CorrelationHeader = None,
        traceparent: TraceparentHeader = None,
    ) -> Any:
        body = await request.app.state.container.queries.get_event(eventId, context(request, Principal("anonymous", ())))
        version = int(body.get("resourceVersion", 1))
        return JSONResponse(jsonable_encoder(body), headers={"ETag": f'"{version}"'})

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
        correlation_id: CorrelationHeader = None,
        traceparent: TraceparentHeader = None,
    ) -> Any:
        command = PlaceBookingCommand(
            payload.customerId,
            payload.eventId,
            tuple(payload.seatIds),
            payload.paymentMethodToken,
            idempotency_key,
        )
        result = await request.app.state.container.booking_saga.execute(command, context(request, principal))
        booking_id = result.body.get("bookingId")
        if booking_id is None:
            return JSONResponse(dict(result.body), status_code=result.status_code)
        provider = await request.app.state.container.bookings.get_booking(str(booking_id), context(request, principal))
        headers = {"ETag": f'"{int(provider.get("resourceVersion", 1))}"'}
        if result.status_code == 202:
            # The outcome is still being reconciled: point the client at the resource
            # to poll instead of letting it resubmit the booking command.
            headers["Location"] = f"/api/bookings/{booking_id}"
            headers["Retry-After"] = str(request.app.state.retry_after_seconds)
        return JSONResponse(
            dict(result.body),
            status_code=result.status_code,
            headers=headers,
        )

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
        correlation_id: CorrelationHeader = None,
        traceparent: TraceparentHeader = None,
    ) -> Any:
        ctx = context(request, principal)
        body = await request.app.state.container.queries.get_booking(bookingId, ctx)
        provider = await request.app.state.container.bookings.get_booking(bookingId, ctx)
        return JSONResponse(
            jsonable_encoder(body),
            headers={"ETag": f'"{int(provider.get("resourceVersion", 1))}"'},
        )

    @router.post(
        "/api/bookings/{bookingId}/cancel",
        operation_id="publicCancelBooking",
        response_model=BookingResult,
        responses=errors(403, 404, 409, 412, 503),
    )
    async def cancel_booking(
        bookingId: str,
        request: Request,
        principal: Annotated[Principal, Security(bearer_principal)],
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
        if_match: Annotated[str, Header(alias="If-Match", pattern=r'^"[1-9][0-9]*"$')],
        correlation_id: CorrelationHeader = None,
        traceparent: TraceparentHeader = None,
    ) -> Any:
        ctx = context(request, principal)
        result = await request.app.state.container.cancellation_saga.execute(
            bookingId, idempotency_key, ctx, expected_version=int(if_match.strip('"'))
        )
        provider = await request.app.state.container.bookings.get_booking(bookingId, ctx)
        return JSONResponse(
            dict(result.body),
            status_code=result.status_code,
            headers={"ETag": f'"{int(provider.get("resourceVersion", 1))}"'},
        )

    @router.get("/api/health", operation_id="aggregateHealth", responses=errors(503))
    async def health(
        request: Request,
        correlation_id: CorrelationHeader = None,
        traceparent: TraceparentHeader = None,
    ) -> Response:
        # Fan-out and policy live in the health service; the router only serializes.
        report = await request.app.state.container.health.aggregate()
        body = AggregateHealthStatus(
            status=report.status.value,
            checkedAt=report.checked_at,
            dependencies=[
                DependencyHealthStatus(
                    name=item.name,
                    critical=item.critical,
                    status=item.state.value,
                    latencyMs=item.latency_ms,
                    errorCode=item.error_code,
                )
                for item in report.dependencies
            ],
        )
        return JSONResponse(
            jsonable_encoder(body),
            status_code=report.http_status,
            headers={"ETag": '"1"'},
        )

    @router.get("/health/live", operation_id="esbLiveness")
    async def liveness(
        correlation_id: CorrelationHeader = None,
        traceparent: TraceparentHeader = None,
    ) -> Response:
        return JSONResponse({"status": "UP"}, headers={"ETag": '"1"'})

    @router.get("/health/ready", operation_id="esbReadiness", responses=errors(503))
    async def readiness(
        request: Request,
        correlation_id: CorrelationHeader = None,
        traceparent: TraceparentHeader = None,
    ) -> Response:
        database = request.app.state.container.database
        if database is not None:
            try:
                await database.ping()
            except Exception as exc:  # noqa: BLE001 -- readiness normalizes driver failures
                raise DependencyFailure(
                    "DEPENDENCY_UNAVAILABLE",
                    "Workflow persistence is unavailable.",
                    503,
                    True,
                ) from exc
        return JSONResponse({"status": "READY"}, headers={"ETag": '"1"'})

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
        correlation_id: CorrelationHeader = None,
        traceparent: TraceparentHeader = None,
    ) -> Any:
        body = await request.app.state.container.queries.trace(correlationId, context(request, principal))
        return JSONResponse(jsonable_encoder(body), headers={"ETag": '"1"'})

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
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)],
        correlation_id: CorrelationHeader = None,
        traceparent: TraceparentHeader = None,
    ) -> Any:
        # The canonical public contract makes X-Correlation-ID optional; the ingress
        # middleware derives one when the browser does not supply it.
        ctx = context(request, principal)
        decision = await request.app.state.container.bookings.decide_access(payload.bookingId, ctx)
        if not decision.get("allowed"):
            raise AccessDenied()
        ticket, expires = request.app.state.container.ws_tickets.issue(principal.subject, payload.bookingId)
        return JSONResponse(
            jsonable_encoder({"ticket": ticket, "bookingId": payload.bookingId, "expiresAt": expires}),
            status_code=201,
            headers={"ETag": '"1"'},
        )

    return router
