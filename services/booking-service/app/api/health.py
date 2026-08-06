"""Process and dependency health endpoints."""

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse

from app import __version__
from app.config import Settings
from app.infrastructure.database.session import database_ready
from app.observability.metrics import READINESS


def create_health_router(settings: Settings) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get("/health/live", operation_id="bookingLiveness")
    async def live() -> dict[str, str]:
        return {
            "service": settings.app_name,
            "status": "UP",
            "version": __version__,
        }

    @router.get("/health/ready", operation_id="bookingReadiness")
    async def ready(request: Request) -> JSONResponse:
        if request.app.state.draining:
            READINESS.set(0)
            return JSONResponse(
                {"service": settings.app_name, "status": "DRAINING"},
                status_code=503,
            )
        healthy = await run_in_threadpool(database_ready, settings)
        READINESS.set(1 if healthy else 0)
        return JSONResponse(
            {
                "service": settings.app_name,
                "status": "READY" if healthy else "NOT_READY",
                "version": __version__,
            },
            status_code=200 if healthy else 503,
        )

    return router
