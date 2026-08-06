"""Bounded access logging and HTTP metrics."""

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from app.observability.metrics import REQUEST_DURATION, REQUEST_TOTAL

LOGGER = logging.getLogger("payment.access")


async def access_log_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    started = time.perf_counter()
    response: Response | None = None
    try:
        response = await call_next(request)
        return response
    finally:
        duration = time.perf_counter() - started
        route = getattr(request.scope.get("route"), "path", "unmatched")
        status_code = response.status_code if response is not None else 500
        REQUEST_TOTAL.labels(request.method, route, f"{status_code // 100}xx").inc()
        REQUEST_DURATION.labels(request.method, route).observe(duration)
        LOGGER.info(
            "HTTP request completed",
            extra={
                "method": request.method,
                "route": route,
                "status_code": status_code,
                "duration_ms": round(duration * 1_000, 2),
            },
        )
