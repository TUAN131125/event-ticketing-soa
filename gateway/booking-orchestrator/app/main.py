from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.adapters.rest.base import RestClient
from app.adapters.rest.identity import IdentityProxyAdapter
from app.adapters.rest.providers import (
    BookingAdapter,
    CustomerAdapter,
    EventAdapter,
    PaymentAdapter,
    RealtimeAdapter,
    TicketAdapter,
    NotificationWebhookSubscriber,
    RealtimeStatusSubscriber,
)
from app.adapters.soap.seat import SeatSoapAdapter
from app.api.http import context_middleware
from app.api.router import router
from app.application.booking import BookingSaga
from app.application.cancellation import CancellationSaga
from app.application.queries import QueryService
from app.application.health import AggregateHealthService
from app.config import Settings
from app.messaging.event_publisher import TopicPublisher
from app.observability.metrics import Metrics
from app.persistence.repositories import repository_from_url
from app.registry.service_registry import ServiceRegistry
from app.resilience.policies import ResiliencePolicy
from app.security.auth import JwtVerifier
from app.security.rate_limit import SlidingWindowLimiter
from app.security.openapi import install_security_openapi
from app.security.service_token import ServiceTokenProvider, load_optional_secret
from app.security.ws_ticket import WebSocketTicketIssuer
from app.workers.outbox import OutboxWorker
from app.workers.reconciliation import ReconciliationWorker


@dataclass(slots=True)
class Container:
    registry: object
    identity: object
    customer: object
    event: object
    seat: object
    booking: object
    payment: object
    ticket: object
    realtime: object
    workflows: object
    outbox: object
    auth: object
    limiter: object
    publisher: object
    booking_saga: object
    cancellation: object
    queries: object
    outbox_worker: object
    reconciliation_worker: object
    health: object
    ws_ticket_issuer: object


def build_container(settings: Settings, repo=None, auth=None) -> Container:
    registry = ServiceRegistry(settings)
    policy = ResiliencePolicy(
        settings.max_safe_read_attempts,
        settings.max_idempotent_command_attempts,
        settings.bulkhead_limit,
    )

    internal_private_key = load_optional_secret(
        settings.internal_service_private_key,
        settings.internal_service_private_key_path,
        "ESB_INTERNAL_SERVICE_PRIVATE_KEY",
    )
    credentials = ServiceTokenProvider(
        private_key=internal_private_key,
        static_token=settings.service_token,
        issuer=settings.internal_service_issuer,
        subject=settings.internal_service_subject,
        key_id=settings.internal_service_key_id,
    )

    def rest_client(name: str) -> RestClient:
        endpoint = registry.resolve(name)
        return RestClient(
            name,
            endpoint.base_url,
            policy,
            credentials,
            endpoint.audience,
            settings.dependency_timeout_seconds,
        )

    identity = IdentityProxyAdapter(
        registry.resolve("identity").base_url,
        policy,
        settings.dependency_timeout_seconds,
    )
    customer = CustomerAdapter(rest_client("customer"))
    event = EventAdapter(rest_client("event"))
    seat = SeatSoapAdapter(
        registry.resolve("seat").base_url,
        policy,
        credentials=credentials,
        audience=registry.resolve("seat").audience,
        dependency_timeout_seconds=settings.dependency_timeout_seconds,
        xsd_path=settings.seat_provider_xsd_path,
    )
    booking = BookingAdapter(rest_client("booking"))
    payment = PaymentAdapter(rest_client("payment"))
    ticket = TicketAdapter(rest_client("ticket"))
    realtime = RealtimeAdapter(rest_client("realtime"))
    repository = repo or repository_from_url(settings.database_url)
    verifier = auth or JwtVerifier(
        settings.jwt_issuer,
        settings.jwt_audience,
        settings.jwks_url,
        settings.jwt_shared_secret,
    )
    limiter = SlidingWindowLimiter()
    notification_secret = settings.notification_webhook_secret
    if not notification_secret:
        notification_secret = "development-only-notification-secret-change-me"
    publisher = TopicPublisher(
        {
            "booking.confirmed": [
                NotificationWebhookSubscriber(
                    rest_client("notification"),
                    notification_secret,
                )
            ],
            "booking.status": [RealtimeStatusSubscriber(rest_client("realtime"))],
        }
    )
    saga = BookingSaga(
        customer,
        event,
        seat,
        booking,
        payment,
        ticket,
        repository,
        repository,
        settings,
    )
    cancellation = CancellationSaga(booking, payment, seat, ticket, customer)
    queries = QueryService(event, seat, booking, ticket, customer)
    outbox_worker = OutboxWorker(
        repository,
        publisher,
        max_attempts=settings.outbox_max_attempts,
        batch_size=settings.outbox_batch_size,
    )
    reconciliation_worker = ReconciliationWorker(
        repository,
        saga,
        interval_seconds=settings.reconciliation_poll_seconds,
        batch_size=settings.reconciliation_batch_size,
    )
    health = AggregateHealthService(
        registry,
        repository=repository,
        timeout_seconds=min(2.0, settings.dependency_timeout_seconds),
    )
    ws_private_key = load_optional_secret(
        settings.ws_ticket_private_key,
        settings.ws_ticket_private_key_path,
        "ESB_WS_TICKET_PRIVATE_KEY",
    )
    ws_ticket_issuer = WebSocketTicketIssuer(
        settings.ws_ticket_signing_secret,
        repository,
        issuer=settings.ws_ticket_issuer,
        audience=settings.ws_ticket_audience,
        ttl_seconds=settings.ws_ticket_ttl_seconds,
        private_key=ws_private_key,
        key_id=settings.ws_ticket_key_id,
    )
    return Container(
        registry,
        identity,
        customer,
        event,
        seat,
        booking,
        payment,
        ticket,
        realtime,
        repository,
        repository,
        verifier,
        limiter,
        publisher,
        saga,
        cancellation,
        queries,
        outbox_worker,
        reconciliation_worker,
        health,
        ws_ticket_issuer,
    )


def create_app(settings: Settings | None = None, container=None) -> FastAPI:
    settings = settings or Settings.from_env()
    settings.validate()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    runtime = container or build_container(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        stop = asyncio.Event()
        tasks: list[asyncio.Task] = []
        initialize = getattr(runtime.workflows, "initialize", None)
        if initialize is not None:
            await initialize()
        if settings.enable_workers:
            tasks = [
                asyncio.create_task(runtime.outbox_worker.run_forever(stop)),
                asyncio.create_task(runtime.reconciliation_worker.run_forever(stop)),
            ]
        try:
            yield
        finally:
            stop.set()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            dispose = getattr(runtime.workflows, "dispose", None)
            if dispose is not None:
                await dispose()

    app = FastAPI(
        title="ESB / Booking Orchestrator",
        version="2.2.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings
    app.state.metrics = Metrics()
    app.state.container = runtime

    @app.exception_handler(RequestValidationError)
    async def request_validation_error(request: Request, exc: RequestValidationError):
        safe_errors = [
            {
                "location": [str(part) for part in error.get("loc", ())],
                "message": str(error.get("msg", "Invalid request")),
                "type": str(error.get("type", "validation_error")),
            }
            for error in exc.errors()
        ]
        return JSONResponse(
            {
                "correlationId": getattr(request.state, "correlation_id", "unknown"),
                "traceId": getattr(request.state, "trace_id", None),
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "retryable": False,
                    "details": {"errors": safe_errors},
                },
            },
            status_code=422,
        )
    origins = settings.origin_list()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "Idempotency-Key",
                "If-Match",
                "X-CSRF-Token",
                "traceparent",
                "X-Correlation-ID",
            ],
            expose_headers=[
                "ETag",
                "Location",
                "Retry-After",
                "X-Correlation-ID",
                "X-Trace-ID",
                "traceparent",
            ],
        )
    app.middleware("http")(context_middleware)
    app.include_router(router)
    install_security_openapi(app)
    # This callable is the actual FastAPI-generated contract. It is never replaced
    # by a YAML file, so CI can detect implementation drift.
    app.state.generated_openapi = app.openapi
    return app
