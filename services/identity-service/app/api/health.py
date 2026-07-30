"""Liveness and readiness endpoints."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.config import Settings
from app.infrastructure.database.session import database_ready
from app.observability.metrics import READINESS
from app.schemas.common import HealthResponse


def create_health_router(settings: Settings) -> APIRouter:
    router = APIRouter(tags=["health"])

    @router.get(
        "/health/live", response_model=HealthResponse, operation_id="healthLive"
    )
    def live() -> HealthResponse:
        return HealthResponse(
            service=settings.app_name, status="UP", version=__version__
        )

    @router.get("/health/ready", operation_id="healthReady")
    def ready(request: Request) -> JSONResponse:
        draining = bool(getattr(request.app.state, "draining", False))
        healthy = not draining and database_ready(settings)
        READINESS.set(1 if healthy else 0)
        return JSONResponse(
            status_code=200 if healthy else 503,
            content={
                "service": settings.app_name,
                "status": "READY"
                if healthy
                else ("DRAINING" if draining else "NOT_READY"),
                "version": __version__,
            },
        )

    return router
