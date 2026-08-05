"""FastAPI application for SOAP Seat Inventory and its admin control plane."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Header, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, ConfigDict, Field

from app import __version__
from app.application.common import RequestContext
from app.application.configure_inventory import (
    SeatDefinition,
    configure_inventory,
)
from app.application.executor import execute_database_operation
from app.config import Settings, get_settings
from app.domain.exceptions import InternalFailure, SeatInventoryError
from app.domain.seat import SeatStatus
from app.infrastructure.database.session import database_ready, dispose_engine
from app.infrastructure.scheduler import expiry_loop
from app.observability.logs import configure_logging
from app.observability.metrics import OPERATION_DURATION, OPERATION_TOTAL, READINESS
from app.observability.tracing import (
    reset_correlation_id,
    sanitize_correlation_id,
    set_correlation_id,
)
from app.security.service_authentication import authenticate_service
from app.soap.service import create_soap_router

LOGGER = logging.getLogger(__name__)


class AdminSeatDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seat_id: str = Field(alias="seatId", min_length=1, max_length=128)
    section: str = Field(min_length=1, max_length=80)
    row_label: str = Field(alias="rowLabel", min_length=1, max_length=40)
    seat_number: str = Field(alias="seatNumber", min_length=1, max_length=40)
    ticket_type: str = Field(alias="ticketType", min_length=1, max_length=80)
    status: Literal["AVAILABLE", "BLOCKED"] = "AVAILABLE"


class ConfigureInventoryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(alias="eventId", min_length=1, max_length=128)
    inventory_version: int = Field(alias="inventoryVersion", ge=1)
    seats: list[AdminSeatDefinition] = Field(min_length=1, max_length=20_000)


def create_app(settings: Settings | None = None) -> FastAPI:
    current = settings or get_settings()
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
        title="Seat Inventory Service Admin API",
        version=__version__,
        docs_url="/admin/docs",
        openapi_url="/admin/openapi.json",
        lifespan=lifespan,
    )
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

    @application.get("/health/live")
    async def live() -> dict[str, str]:
        return {"service": current.app_name, "status": "UP", "version": __version__}

    @application.get("/health/ready")
    async def ready(request: Request) -> JSONResponse:
        if request.app.state.draining:
            READINESS.set(0)
            return JSONResponse({"status": "DRAINING"}, status_code=503)
        healthy = await run_in_threadpool(database_ready, current)
        READINESS.set(1 if healthy else 0)
        return JSONResponse(
            {"status": "READY" if healthy else "NOT_READY"},
            status_code=200 if healthy else 503,
        )

    @application.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @application.post("/admin/inventory")
    async def configure_inventory_endpoint(
        body: ConfigureInventoryBody,
        x_service_token: str | None = Header(default=None, alias="X-Service-Token"),
        x_correlation_id: str | None = Header(default=None, alias="X-Correlation-ID"),
        x_actor_id: str | None = Header(default=None, alias="X-Actor-ID"),
    ) -> JSONResponse:
        started = time.perf_counter()
        operation = "ConfigureInventory"
        try:
            authenticate_service(x_service_token, current.service_token)
            context = RequestContext(
                correlation_id=sanitize_correlation_id(x_correlation_id),
                caller_service="admin-api",
                actor_id=x_actor_id,
                schema_version="1.0",
            )
            definitions = tuple(
                SeatDefinition(
                    seat_id=seat.seat_id,
                    section=seat.section,
                    row_label=seat.row_label,
                    seat_number=seat.seat_number,
                    ticket_type=seat.ticket_type,
                    status=SeatStatus(seat.status),
                )
                for seat in body.seats
            )
            result = await run_in_threadpool(
                execute_database_operation,
                current,
                lambda session: configure_inventory(
                    session,
                    current,
                    context,
                    event_id=body.event_id,
                    inventory_version=body.inventory_version,
                    seats=definitions,
                ),
            )
            OPERATION_TOTAL.labels(operation, "success").inc()
            LOGGER.info(
                "Inventory configured",
                extra={
                    "operation": operation,
                    "event_id": result.event_id,
                    "seat_count": result.seat_count,
                    "result": "SUCCESS",
                    "duration_ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
            return JSONResponse(
                {
                    "eventId": result.event_id,
                    "inventoryVersion": result.inventory_version,
                    "seatCount": result.seat_count,
                    "correlationId": context.correlation_id,
                }
            )
        except SeatInventoryError as exc:
            OPERATION_TOTAL.labels(operation, "fault").inc()
            return JSONResponse(
                {
                    "code": exc.code,
                    "message": exc.message,
                    "correlationId": sanitize_correlation_id(x_correlation_id),
                    "retryable": exc.retryable,
                },
                status_code=exc.http_status,
            )
        except Exception:
            error = InternalFailure()
            OPERATION_TOTAL.labels(operation, "error").inc()
            LOGGER.exception(
                "ConfigureInventory failed",
                extra={
                    "operation": operation,
                    "result": "ERROR",
                    "error_code": error.code,
                },
            )
            return JSONResponse(
                {
                    "code": error.code,
                    "message": error.message,
                    "correlationId": sanitize_correlation_id(x_correlation_id),
                    "retryable": False,
                },
                status_code=500,
            )
        finally:
            OPERATION_DURATION.labels(operation).observe(time.perf_counter() - started)

    return application
