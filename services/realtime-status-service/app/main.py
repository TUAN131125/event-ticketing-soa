"""FastAPI entrypoint for the best-effort Realtime Status Service."""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from app import __version__
from app.broadcast.backends import BroadcastBackend, InMemoryBroadcastBackend, RedisBroadcastBackend
from app.config import Settings, get_settings
from app.consumers.booking_status_consumer import StatusEventProcessor
from app.errors import (
    Forbidden,
    InvalidRequest,
    PublishUnavailable,
    RequestTooLarge,
    Unauthenticated,
)
from app.middleware.http import install_error_handlers, request_context_middleware
from app.observability.logs import configure_logging
from app.observability.metrics import BROADCAST_FAILURES, INTERNAL_EVENTS, READINESS
from app.schemas.messages import EventIngestResponse, RealtimeStatusEvent, ShutdownControl
from app.security.booking_access import BookingAccessChecker, HttpBookingAccessChecker
from app.security.ticket_replay import (
    InMemoryTicketReplayStore,
    RedisTicketReplayStore,
    TicketReplayStore,
)
from app.security.token_validation import JwksTokenValidator, TokenValidator
from app.security.ws_ticket import SignedWebSocketTicketValidator, WebSocketTicketValidator
from app.websocket.connection_manager import ConnectionManager
from app.websocket.endpoint import CLOSE_SERVER_SHUTDOWN, create_websocket_router
from app.websocket.heartbeat import HeartbeatRunner
from app.websocket.subscriptions import HandshakeRateLimiter


async def _cleanup_loop(processor: StatusEventProcessor, interval: float) -> None:
    try:
        while True:
            await asyncio.sleep(interval)
            await processor.cleanup()
    except asyncio.CancelledError:
        raise


async def _bounded_body(request: Request, limit: int) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > limit:
                raise RequestTooLarge()
        except ValueError:
            raise InvalidRequest("Content-Length is invalid") from None
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit:
            raise RequestTooLarge()
    return bytes(body)


def _authenticate_internal(settings: Settings, token: str | None, caller: str | None) -> str:
    if token is None or not secrets.compare_digest(token, settings.internal_service_token):
        raise Unauthenticated()
    if caller is None:
        raise InvalidRequest("X-Caller-Service header is required")
    if caller not in settings.allowed_internal_callers:
        raise Forbidden("Caller service is not allowed")
    return caller


def create_app(
    settings: Settings | None = None,
    *,
    token_validator: TokenValidator | None = None,
    access_checker: BookingAccessChecker | None = None,
    broadcast_backend: BroadcastBackend | None = None,
    ws_ticket_validator: WebSocketTicketValidator | None = None,
    ticket_replay_store: TicketReplayStore | None = None,
) -> FastAPI:
    current = settings or get_settings()
    configure_logging(current.log_level)

    manager = ConnectionManager(
        max_connections=current.max_connections,
        max_per_principal=current.max_connections_per_principal,
        max_per_ip=current.max_connections_per_ip,
        send_timeout=current.send_timeout_seconds,
    )
    backend: BroadcastBackend
    if broadcast_backend is not None:
        backend = broadcast_backend
    elif current.redis_url:
        backend = RedisBroadcastBackend(
            manager,
            redis_url=current.redis_url,
            channel=current.redis_channel,
            authoritative_url_template=current.authoritative_booking_url_template,
            dedup_ttl=current.dedup_ttl_seconds,
            dedup_max_entries=current.dedup_max_entries,
        )
    else:
        backend = InMemoryBroadcastBackend(manager, current.authoritative_booking_url_template)
    processor = StatusEventProcessor(
        backend,
        dedup_ttl=current.dedup_ttl_seconds,
        dedup_max_entries=current.dedup_max_entries,
        sequence_ttl=current.sequence_cache_ttl_seconds,
        sequence_max_entries=current.sequence_max_entries,
    )
    replay_store = ticket_replay_store or (
        RedisTicketReplayStore(current.redis_url)
        if current.redis_url
        else InMemoryTicketReplayStore(current.ws_ticket_replay_max_entries)
    )
    configured_ticket_validator = ws_ticket_validator
    if configured_ticket_validator is None and current.ws_ticket_public_key_path is not None:
        configured_ticket_validator = SignedWebSocketTicketValidator(
            public_key_path=current.ws_ticket_public_key_path,
            issuer=current.ws_ticket_issuer,
            audience=current.ws_ticket_audience,
            key_id=current.ws_ticket_key_id,
            max_ttl_seconds=current.ws_ticket_max_ttl_seconds,
        )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.draining = False
        await backend.start()
        await replay_store.start()
        cleanup_task = asyncio.create_task(
            _cleanup_loop(processor, current.cleanup_interval_seconds),
            name="realtime-cache-cleanup",
        )
        application.state.cleanup_task = cleanup_task
        try:
            yield
        finally:
            application.state.draining = True
            READINESS.set(0)
            await backend.stop()
            await replay_store.stop()
            shutdown_payload = ShutdownControl().model_dump(mode="json")
            try:
                await asyncio.wait_for(
                    manager.begin_shutdown(shutdown_payload, CLOSE_SERVER_SHUTDOWN),
                    timeout=current.graceful_shutdown_timeout_seconds,
                )
            except TimeoutError:
                pass
            cleanup_task.cancel()
            await asyncio.gather(cleanup_task, return_exceptions=True)

    application = FastAPI(
        title="Realtime Status Service",
        version=__version__,
        docs_url="/docs" if current.docs_enabled else None,
        openapi_url="/openapi.json" if current.docs_enabled else None,
        lifespan=lifespan,
    )
    application.state.settings = current
    application.state.draining = False
    application.state.connection_manager = manager
    application.state.broadcast_backend = backend
    application.state.event_processor = processor
    application.state.token_validator = token_validator or JwksTokenValidator(current)
    application.state.access_checker = access_checker or HttpBookingAccessChecker(current)
    application.state.ws_ticket_validator = configured_ticket_validator
    application.state.ticket_replay_store = replay_store
    application.state.handshake_limiter = HandshakeRateLimiter(
        current.handshake_rate_limit, current.handshake_rate_window_seconds
    )
    application.state.heartbeat = HeartbeatRunner(
        manager,
        interval=current.heartbeat_interval_seconds,
        idle_timeout=current.idle_timeout_seconds,
    )

    application.add_middleware(BaseHTTPMiddleware, dispatch=request_context_middleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(current.allowed_ws_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "X-Service-Token",
            "X-Caller-Service",
            "X-Correlation-ID",
            "traceparent",
        ],
        expose_headers=["X-Correlation-ID"],
    )
    application.include_router(create_websocket_router())

    @application.post(
        "/internal/status-events",
        response_model=EventIngestResponse,
        status_code=202,
        tags=["internal"],
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {
                    "application/json": {"schema": RealtimeStatusEvent.model_json_schema()}
                },
            }
        },
    )
    async def ingest_status_event(
        request: Request,
        x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
        x_caller_service: str | None = Header(default=None, alias="X-Caller-Service"),
    ) -> EventIngestResponse:
        _authenticate_internal(current, x_service_token, x_caller_service)
        content_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
        if content_type != "application/json":
            raise InvalidRequest("Content-Type must be application/json")
        body = await _bounded_body(request, current.max_event_bytes)
        try:
            event = RealtimeStatusEvent.model_validate(json.loads(body))
        except (ValidationError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            INTERNAL_EVENTS.labels("validation_error").inc()
            raise InvalidRequest("Status event payload is invalid") from exc
        INTERNAL_EVENTS.labels("received").inc()
        try:
            result = await processor.process(event)
        except (RuntimeError, OSError) as exc:
            INTERNAL_EVENTS.labels("publish_failure").inc()
            BROADCAST_FAILURES.labels(backend.name).inc()
            raise PublishUnavailable() from exc
        INTERNAL_EVENTS.labels(result.outcome).inc()
        return EventIngestResponse(
            correlationId=getattr(request.state, "correlation_id", event.correlation_id),
            outcome=result.outcome,
            broadcast=result.broadcast,
            sequenceGap=result.sequence_gap,
        )

    @application.get("/connections/health", tags=["health"])
    async def connections_health() -> dict[str, Any]:
        stats = await manager.stats()
        return {
            "service": current.app_name,
            "status": "DRAINING" if application.state.draining else "UP",
            **stats,
            "broadcastBackend": backend.name,
            "redisAvailability": backend.availability(),
        }

    @application.get("/health/live", tags=["health"])
    async def liveness() -> dict[str, str]:
        return {"service": current.app_name, "status": "UP", "version": __version__}

    @application.get("/health/ready", tags=["health"])
    async def readiness() -> Response:
        ready = not application.state.draining and (not current.redis_required or backend.ready())
        READINESS.set(1 if ready else 0)
        return Response(
            content=json.dumps(
                {
                    "service": current.app_name,
                    "status": "READY" if ready else "NOT_READY",
                    "version": __version__,
                }
            ),
            media_type="application/json",
            status_code=200 if ready else 503,
        )

    @application.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    install_error_handlers(application)
    return application


app = create_app()
