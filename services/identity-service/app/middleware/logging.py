"""Request metrics and access logs using route templates."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import Request

from app.observability.metrics import REQUEST_DURATION, REQUESTS

LOGGER = logging.getLogger(__name__)


def _operation_name(request: Request) -> str:
    route: Any = request.scope.get("route")
    return str(
        getattr(route, "operation_id", None)
        or getattr(route, "path", None)
        or "unmatched"
    )


async def access_log_middleware(
    request: Request, call_next
):  # type: ignore[no-untyped-def]
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        return response
    finally:
        operation = _operation_name(request)
        duration_seconds = time.perf_counter() - started
        REQUESTS.labels(operation, str(status_code)).inc()
        REQUEST_DURATION.labels(operation).observe(duration_seconds)
        LOGGER.info(
            "Request completed",
            extra={
                "operation": operation,
                "method": request.method,
                "status": status_code,
                "durationMs": round(duration_seconds * 1000, 2),
            },
        )
