"""Canonical liveness and readiness probes."""

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from libs.platform_http import HealthStatus, error_envelope

from app.infrastructure.database.session import database_ready

router = APIRouter(tags=["health"])


@router.get(
    "/health/live", operation_id="customerLiveness", response_model=HealthStatus
)
def liveness() -> HealthStatus:
    return HealthStatus(status="UP")


@router.get(
    "/health/ready", operation_id="customerReadiness", response_model=HealthStatus
)
def readiness(request: Request) -> Response:
    if database_ready(request.app.state.settings):
        return JSONResponse({"status": "READY"})
    return JSONResponse(
        error_envelope(
            request,
            code="SERVICE_UNAVAILABLE",
            message="Customer database is not ready",
            retryable=True,
        ),
        status_code=503,
    )
