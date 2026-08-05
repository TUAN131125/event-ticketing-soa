"""FastAPI application for the canonical SOAP Seat Inventory boundary."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from libs.platform_http import HealthStatus, error_envelope
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app import __version__
from app.config import Settings, get_settings
from app.infrastructure.database.session import database_ready, dispose_engine
from app.infrastructure.scheduler import expiry_loop
from app.observability.logs import configure_logging
from app.observability.metrics import READINESS
from app.observability.tracing import (
    reset_correlation_id,
    sanitize_correlation_id,
    set_correlation_id,
)
from app.soap.service import create_soap_router


def create_app(settings: Settings | None = None) -> FastAPI:
    current = settings or get_settings()
    service_jwt_verifier = current.service_jwt.verifier()
    configure_logging(current.log_level)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        application.state.draining = False
        application.state.stop_event = asyncio.Event()
        worker: asyncio.Task[None] | None = None
        if current.expiry_worker_enabled:
            worker = asyncio.create_task(
                expiry_loop(current, application.state.stop_event),
                name="seat-expiry-worker",
            )
        try:
            yield
        finally:
            application.state.draining = True
            application.state.stop_event.set()
            if worker is not None:
                try:
                    await asyncio.wait_for(worker, timeout=10)
                except TimeoutError:
                    worker.cancel()
            await asyncio.to_thread(dispose_engine)

    application = FastAPI(
        title="Seat Inventory Service",
        version=__version__,
        docs_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    application.state.service_jwt_verifier = service_jwt_verifier
    application.include_router(create_soap_router(current))

    @application.middleware("http")
    async def correlation_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        correlation_id = sanitize_correlation_id(
            request.headers.get("X-Correlation-ID")
        )
        token = set_correlation_id(correlation_id)
        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            return response
        finally:
            reset_correlation_id(token)

    @application.get("/health/live", response_model=HealthStatus)
    async def live() -> HealthStatus:
        return HealthStatus(service=current.app_name, status="UP", version=__version__)

    @application.get("/health/ready")
    async def ready(request: Request) -> JSONResponse:
        if request.app.state.draining:
            READINESS.set(0)
            return JSONResponse(
                error_envelope(
                    request,
                    code="SERVICE_UNAVAILABLE",
                    message="Seat Inventory service is draining",
                    retryable=True,
                ),
                status_code=503,
            )
        healthy = await run_in_threadpool(database_ready, current)
        READINESS.set(1 if healthy else 0)
        if healthy:
            return JSONResponse({"status": "READY"})
        return JSONResponse(
            error_envelope(
                request,
                code="SERVICE_UNAVAILABLE",
                message="Seat Inventory database is not ready",
                retryable=True,
            ),
            status_code=503,
        )

    @application.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return application
