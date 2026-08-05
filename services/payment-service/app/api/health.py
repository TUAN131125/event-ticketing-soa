"""Process and dependency health endpoints."""

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from libs.platform_http import HealthStatus, error_envelope

from app import __version__
from app.config import Settings
from app.infrastructure.database.session import database_ready
from app.observability.metrics import READINESS


def create_health_router(settings: Settings) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get(
        "/health/live", operation_id="paymentLiveness", response_model=HealthStatus
    )
    async def live() -> HealthStatus:
        return HealthStatus(service=settings.app_name, status="UP", version=__version__)

    @router.get(
        "/health/ready", operation_id="paymentReadiness", response_model=HealthStatus
    )
    async def ready(request: Request) -> JSONResponse:
        if request.app.state.draining:
            READINESS.set(0)
            return JSONResponse(
                error_envelope(
                    request,
                    code="SERVICE_UNAVAILABLE",
                    message="Payment service is draining",
                    retryable=True,
                ),
                status_code=503,
            )
        healthy = await run_in_threadpool(database_ready, settings)
        READINESS.set(1 if healthy else 0)
        if healthy:
            return JSONResponse(
                {
                    "service": settings.app_name,
                    "status": "READY",
                    "version": __version__,
                }
            )
        return JSONResponse(
            error_envelope(
                request,
                code="SERVICE_UNAVAILABLE",
                message="Payment database is not ready",
                retryable=True,
            ),
            status_code=503,
        )

    return router
