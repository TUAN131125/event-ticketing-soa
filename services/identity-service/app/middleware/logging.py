"""Request metrics and access logs using route templates."""

from __future__ import annotations

import logging
import time

from fastapi import Request

from app.observability.metrics import REQUEST_DURATION, REQUESTS

LOGGER = logging.getLogger(__name__)


async def access_log_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    started = time.perf_counter()
    response = await call_next(request)
    route = request.scope.get("route")
    operation = getattr(route, "path", "unmatched")
    status = str(response.status_code)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    REQUESTS.labels(operation, status).inc()
    REQUEST_DURATION.labels(operation).observe(duration_ms / 1000)
    LOGGER.info(
        "Request completed",
        extra={
            "operation": operation,
            "method": request.method,
            "status": response.status_code,
            "durationMs": duration_ms,
        },
    )
    return response
