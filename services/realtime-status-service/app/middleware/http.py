"""Correlation propagation, access metrics and safe error envelopes."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.errors import ServiceError
from app.observability.metrics import HTTP_DURATION, HTTP_REQUESTS
from app.observability.tracing import bind, reset, safe_id, trace_id

LOGGER = logging.getLogger("realtime.http")


def error_response(correlation_id: str, error: ServiceError) -> JSONResponse:
    headers = {"X-Correlation-ID": correlation_id}
    if error.http_status == 401:
        headers["WWW-Authenticate"] = "ServiceToken"
    return JSONResponse(
        status_code=error.http_status,
        headers=headers,
        content={
            "correlationId": correlation_id,
            "error": {
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
                "details": error.details,
            },
        },
    )


async def request_context_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    started = time.perf_counter()
    correlation_id = safe_id(request.headers.get("x-correlation-id"))
    trace = trace_id(request.headers.get("traceparent"))
    request.state.correlation_id = correlation_id
    request.state.trace_id = trace
    tokens = bind(correlation_id, trace)
    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        route = request.scope.get("route")
        operation = getattr(route, "path", "unmatched")
        HTTP_REQUESTS.labels(operation, f"{response.status_code // 100}xx").inc()
        HTTP_DURATION.labels(operation).observe(time.perf_counter() - started)
        LOGGER.info(
            "HTTP request completed",
            extra={
                "operation": operation,
                "outcome": str(response.status_code),
                "durationMs": round((time.perf_counter() - started) * 1000, 2),
            },
        )
        return response
    finally:
        reset(tokens)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError) -> JSONResponse:
        return error_response(getattr(request.state, "correlation_id", "unknown"), exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = {
            "violations": [
                {"location": ".".join(map(str, item["loc"])), "type": item["type"]}
                for item in exc.errors()
            ]
        }
        return error_response(
            getattr(request.state, "correlation_id", "unknown"),
            ServiceError("INVALID_REQUEST", "Request validation failed", 422, details=details),
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        LOGGER.exception(
            "Unhandled realtime service error",
            extra={"operation": "http", "outcome": "failure", "errorCode": "INTERNAL_ERROR"},
        )
        return error_response(
            getattr(request.state, "correlation_id", "unknown"),
            ServiceError("INTERNAL_ERROR", "An internal error occurred", 500),
        )
