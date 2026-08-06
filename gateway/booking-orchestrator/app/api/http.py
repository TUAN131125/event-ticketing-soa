from __future__ import annotations

import json
import logging
import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

from app.domain.errors import EsbError
from app.security.trace import parse_trace_id

LOGGER = logging.getLogger("booking_orchestrator.http")


def _log_request(
    *,
    level: int,
    request: Request,
    correlation_id: str,
    trace_id: str,
    status_code: int,
    duration_seconds: float,
    error_code: str | None = None,
) -> None:
    # Do not log headers, request bodies, payment tokens, QR values or PII.
    event = {
        "event": "esb.http.request",
        "method": request.method,
        "path": request.url.path,
        "statusCode": status_code,
        "durationMs": int(duration_seconds * 1000),
        "correlationId": correlation_id,
        "traceId": trace_id,
    }
    if error_code:
        event["errorCode"] = error_code
    LOGGER.log(level, json.dumps(event, separators=(",", ":")))


async def context_middleware(request: Request, call_next):
    correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
    trace_id = parse_trace_id(request.headers.get("traceparent"))
    started = time.monotonic()
    request.state.correlation_id = correlation_id
    request.state.trace_id = trace_id
    request.state.deadline = (
        started + request.app.state.settings.request_timeout_seconds
    )
    error_code: str | None = None
    log_level = logging.INFO

    try:
        response = await call_next(request)
    except EsbError as exc:
        error_code = exc.code
        log_level = logging.WARNING if exc.status_code < 500 else logging.ERROR
        response = JSONResponse(
            {
                "correlationId": correlation_id,
                "traceId": trace_id,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "retryable": exc.retryable,
                    **({"details": exc.details} if exc.details else {}),
                },
            },
            status_code=exc.status_code,
        )
        if exc.status_code == 429 and exc.details and exc.details.get("retryAfter"):
            response.headers["Retry-After"] = str(exc.details["retryAfter"])
    except Exception:
        error_code = "INTERNAL_ERROR"
        log_level = logging.ERROR
        LOGGER.exception(
            "Unhandled ESB request failure",
            extra={"correlation_id": correlation_id, "trace_id": trace_id},
        )
        response = JSONResponse(
            {
                "correlationId": correlation_id,
                "traceId": trace_id,
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "Unexpected ESB error",
                    "retryable": False,
                },
            },
            status_code=500,
        )

    duration = time.monotonic() - started
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["traceparent"] = f"00-{trace_id}-0000000000000001-01"
    request.app.state.metrics.inc(
        "esb_request_total",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
    )
    request.app.state.metrics.observe(
        "esb_request_duration_seconds",
        duration,
        path=request.url.path,
        status=response.status_code,
    )
    _log_request(
        level=log_level,
        request=request,
        correlation_id=correlation_id,
        trace_id=trace_id,
        status_code=response.status_code,
        duration_seconds=duration,
        error_code=error_code,
    )
    return response
