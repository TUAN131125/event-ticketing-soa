from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.responses import Response

from app.domain.errors import EsbError

logger = logging.getLogger(__name__)


def install_http_layer(app: FastAPI, request_timeout_seconds: float) -> None:
    @app.middleware("http")
    async def correlation_and_deadline(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        started = time.perf_counter()
        supplied = request.headers.get("X-Correlation-ID")
        request.state.correlation_id = supplied if supplied and 16 <= len(supplied) <= 64 else uuid4().hex
        request.state.deadline = time.monotonic() + request_timeout_seconds
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request_failed",
                extra={
                    "correlationId": request.state.correlation_id,
                    "traceId": request.headers.get("traceparent"),
                    "operation": request.url.path,
                    "provider": "booking-orchestrator",
                    "outcome": "FAILURE",
                    "duration": int((time.perf_counter() - started) * 1000),
                },
            )
            raise
        response.headers["X-Correlation-ID"] = request.state.correlation_id
        logger.info(
            "request_complete",
            extra={
                "correlationId": request.state.correlation_id,
                "traceId": request.headers.get("traceparent"),
                "operation": request.url.path,
                "provider": "booking-orchestrator",
                "outcome": str(response.status_code),
                "duration": int((time.perf_counter() - started) * 1000),
            },
        )
        return response

    def envelope(
        request: Request,
        code: str,
        message: str,
        retryable: bool,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "correlationId": getattr(request.state, "correlation_id", uuid4().hex),
            "traceId": request.headers.get("traceparent"),
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
                "details": details or {},
            },
        }

    @app.exception_handler(EsbError)
    async def esb_error(request: Request, exc: EsbError) -> JSONResponse:
        return JSONResponse(
            envelope(request, exc.code, exc.message, exc.retryable, dict(exc.details)),
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = {"fields": [{"path": ".".join(map(str, item["loc"])), "type": item["type"]} for item in exc.errors()]}
        return JSONResponse(
            envelope(
                request,
                "VALIDATION_ERROR",
                "Request validation failed.",
                False,
                details,
            ),
            status_code=422,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code = "AUTHENTICATION_REQUIRED" if exc.status_code == 401 else "HTTP_ERROR"
        return JSONResponse(
            envelope(
                request,
                code,
                "Authentication required." if exc.status_code == 401 else "Request failed.",
                False,
            ),
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            envelope(request, "INTERNAL_ERROR", "An internal error occurred.", False),
            status_code=500,
        )
