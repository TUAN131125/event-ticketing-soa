from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.adapters.health import ReadinessProbe
from app.adapters.rest.base import RestClient
from app.adapters.rest.providers import (
    BookingRestAdapter,
    CustomerRestAdapter,
    EventRestAdapter,
    NotificationRestAdapter,
    PaymentRestAdapter,
    RealtimeRestAdapter,
    TicketRestAdapter,
)
from app.adapters.soap.seat import SeatSoapAdapter
from app.api.http import install_http_layer
from app.api.router import create_router
from app.application.booking import BookingSaga
from app.application.cancellation import CancellationSaga
from app.application.health import DatabaseProbe, HealthService
from app.application.queries import QueryService
from app.config import Settings
from app.contract_freeze import verify_contract_freeze
from app.dependencies import RuntimeContainer, SystemClock
from app.observability.logging import configure_logging
from app.persistence.database import Database
from app.persistence.repositories import SqlRepositories
from app.ports.providers import HealthProbe
from app.resilience.policies import (
    Bulkhead,
    CircuitBreaker,
    ResilienceExecutor,
    RetryClass,
)
from app.security.jwt import JwksVerifier, JwtSigner, WebSocketTicketIssuer
from app.workers.outbox import OutboxDispatcher
from app.workers.reconciliation import ReconciliationWorker, RecoveryScanner


def _private_key(value: str | None, path: Path | None, name: str) -> str:
    if value and path:
        raise ValueError(f"configure only one of {name} or {name}_PATH")
    if value:
        return value
    if path is None:
        raise ValueError(f"{name} or {name}_PATH is required")
    try:
        key = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {name}_PATH: {path}") from exc
    if not key.strip():
        raise ValueError(f"{name}_PATH is empty: {path}")
    return key


def _required_value(value: str | None, name: str) -> str:
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _executor(settings: Settings) -> ResilienceExecutor:
    return ResilienceExecutor(
        {
            RetryClass.NONE: 1,
            RetryClass.SAFE_READ: settings.safe_read_attempts,
            RetryClass.IDEMPOTENT_COMMAND: settings.idempotent_command_attempts,
            RetryClass.RECONCILIATION_ONLY: 1,
            RetryClass.SIDE_EFFECT: settings.idempotent_command_attempts,
        },
        settings.retry_base_seconds,
        CircuitBreaker(settings.circuit_failure_threshold, settings.circuit_recovery_seconds),
        Bulkhead(settings.bulkhead_limit),
    )


def build_container(settings: Settings) -> RuntimeContainer:
    http = httpx.AsyncClient(follow_redirects=False)
    database = Database(settings.database_url)
    repositories = SqlRepositories(database)
    clock = SystemClock()
    private_key = _private_key(
        settings.internal_service_private_key,
        settings.internal_service_private_key_path,
        "ESB_INTERNAL_SERVICE_PRIVATE_KEY",
    )
    ws_key = _private_key(
        settings.ws_ticket_private_key,
        settings.ws_ticket_private_key_path,
        "ESB_WS_TICKET_PRIVATE_KEY",
    )
    signer = JwtSigner(
        private_key,
        settings.internal_service_issuer,
        settings.internal_service_subject,
        settings.internal_service_key_id,
    )

    def rest(url: str, audience: str) -> RestClient:
        endpoint = _required_value(url, f"ESB_{audience.upper().replace('-', '_')}_URL")
        return RestClient(
            endpoint,
            audience,
            http,
            signer,
            _executor(settings),
            repositories,
        )

    customer = CustomerRestAdapter(rest(settings.customer_service_url, "customer-service"))
    events = EventRestAdapter(rest(settings.event_service_url, "event-service"))
    bookings = BookingRestAdapter(rest(settings.booking_service_url, "booking-service"))
    payments = PaymentRestAdapter(rest(settings.payment_service_url, "payment-service"))
    tickets = TicketRestAdapter(rest(settings.ticket_service_url, "ticket-service"))
    seats = SeatSoapAdapter(
        _required_value(settings.seat_service_url, "ESB_SEAT_SERVICE_URL"),
        http,
        _executor(settings),
        str(settings.seat_provider_xsd_path),
        signer,
        repositories,
    )
    notification_secret = _required_value(
        settings.notification_webhook_secret,
        "ESB_NOTIFICATION_WEBHOOK_SECRET",
    )
    notification = NotificationRestAdapter(
        rest(settings.notification_service_url, "notification-service"),
        notification_secret,
    )
    realtime = RealtimeRestAdapter(rest(settings.realtime_service_url, "realtime-status-service"))
    saga = BookingSaga(
        customer,
        events,
        seats,
        bookings,
        payments,
        tickets,
        repositories,
        repositories,
        repositories,
        repositories,
        repositories,
        clock,
        settings.idempotent_command_attempts,
        settings.reconciliation_deadline_seconds,
    )
    cancellation = CancellationSaga(
        bookings,
        payments,
        tickets,
        seats,
        repositories,
        repositories,
        repositories,
        clock,
    )
    queries = QueryService(events, bookings, repositories)
    auth = JwksVerifier(
        _required_value(settings.identity_jwks_url, "ESB_IDENTITY_JWKS_URL"),
        settings.identity_expected_issuer,
        settings.identity_expected_audience,
        settings.identity_jwks_cache_seconds,
        http,
    )
    ws = WebSocketTicketIssuer(
        ws_key,
        settings.ws_ticket_issuer,
        settings.ws_ticket_audience,
        settings.ws_ticket_key_id,
        settings.ws_ticket_ttl_seconds,
    )
    outbox = OutboxDispatcher(repositories, notification, realtime, clock)
    reconciliation = ReconciliationWorker(
        repositories,
        repositories,
        seats,
        bookings,
        payments,
        tickets,
        repositories,
        clock,
        settings.reconciliation_backoff_seconds,
        max_backoff_seconds=300,
        lease_seconds=settings.reconciliation_lease_seconds,
    )
    health = HealthService(
        _health_probes(settings, http, database),
        clock,
        settings.health_probe_timeout_seconds,
    )
    return RuntimeContainer(
        saga,
        cancellation,
        queries,
        auth,
        ws,
        bookings,
        health,
        outbox,
        reconciliation,
        database,
        http,
    )


# Booking cannot complete without these; Notification and Realtime only degrade it.
CRITICAL_DEPENDENCIES = (
    ("customer-service", "customer_service_url"),
    ("event-service", "event_service_url"),
    ("seat-inventory-service", "seat_service_url"),
    ("booking-service", "booking_service_url"),
    ("payment-service", "payment_service_url"),
    ("ticket-service", "ticket_service_url"),
)
NONCRITICAL_DEPENDENCIES = (
    ("notification-service", "notification_service_url"),
    ("realtime-status-service", "realtime_service_url"),
)


def _health_probes(settings: Settings, http: httpx.AsyncClient, database: Database | None) -> list[HealthProbe]:
    probes: list[HealthProbe] = [DatabaseProbe(database)]
    for critical, group in ((True, CRITICAL_DEPENDENCIES), (False, NONCRITICAL_DEPENDENCIES)):
        for name, attribute in group:
            probes.append(ReadinessProbe(name, getattr(settings, attribute), http, critical=critical))
    return probes


def create_app(settings: Settings | None = None, container: RuntimeContainer | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)
    if settings.verify_contract_freeze:
        verify_contract_freeze()
    runtime = container or build_container(settings)
    stop = asyncio.Event()
    tasks: list[asyncio.Task[None]] = []

    async def worker_loop(worker: Any, interval: float) -> None:
        while not stop.is_set():
            await worker.run_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                continue

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        if runtime.reconciliation_worker is not None:
            await RecoveryScanner(
                runtime.reconciliation_worker.workflows,
                runtime.reconciliation_worker.jobs,
            ).recover()
        if runtime.outbox_worker:
            tasks.append(asyncio.create_task(worker_loop(runtime.outbox_worker, settings.outbox_poll_seconds)))
        if runtime.reconciliation_worker:
            tasks.append(
                asyncio.create_task(
                    worker_loop(
                        runtime.reconciliation_worker,
                        settings.reconciliation_poll_seconds,
                    )
                )
            )
        yield
        stop.set()
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        if runtime.http_client is not None:
            await runtime.http_client.aclose()
        if runtime.database is not None:
            await runtime.database.dispose()

    app = FastAPI(
        title="Booking ESB Public API",
        version="1.0.0",
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.container = runtime
    app.state.retry_after_seconds = settings.booking_retry_after_seconds
    origins = settings.origin_list()
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "Idempotency-Key",
                "If-Match",
                "traceparent",
                "X-Correlation-ID",
            ],
            # The contract requires clients to read ETag before If-Match, and to poll
            # Location after a 202 instead of resubmitting. Browsers cannot see either
            # header unless it is exposed.
            expose_headers=["ETag", "Location", "Retry-After", "X-Correlation-ID"],
        )
    install_http_layer(app, settings.request_timeout_seconds)
    app.include_router(create_router())
    generated_openapi = app.openapi
    canonical_responses = {
        ("get", "/api/events"): {"200", "500"},
        ("get", "/api/events/{eventId}"): {"200", "404", "503"},
        ("post", "/api/bookings"): {"201", "202", "402", "409", "422", "503"},
        ("get", "/api/bookings/{bookingId}"): {"200", "403", "404"},
        ("post", "/api/bookings/{bookingId}/cancel"): {
            "200",
            "403",
            "404",
            "409",
            "503",
            "412",
        },
        ("get", "/api/health"): {"200", "503"},
        ("get", "/api/traces/{correlationId}"): {"200", "403", "404"},
        ("post", "/api/realtime/ws-tickets"): {
            "201",
            "400",
            "401",
            "403",
            "429",
            "503",
        },
        ("get", "/health/live"): {"200"},
        ("get", "/health/ready"): {"200", "503"},
    }

    def contract_openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            schema = generated_openapi()
            for (method, path), allowed in canonical_responses.items():
                responses = schema["paths"][path][method]["responses"]
                schema["paths"][path][method]["responses"] = {code: response for code, response in responses.items() if code in allowed}
            app.openapi_schema = schema
        return app.openapi_schema

    app.openapi = contract_openapi
    return app
