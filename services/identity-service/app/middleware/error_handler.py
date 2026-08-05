"""Exception handlers that expose only stable error contracts."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.domain.exceptions import DependencyUnavailable, IdentityError
from app.observability.metrics import ERROR_RESPONSES

LOGGER = logging.getLogger(__name__)


def _request_ids(request: Request) -> tuple[str, str]:
    context = getattr(request.state, "identity_context", None)
    if context is None:
        return "-", "-"
    return context.correlation_id, context.trace_id


def _error_response(request: Request, error: IdentityError) -> JSONResponse:
    correlation, trace = _request_ids(request)
    headers = {
        "X-Correlation-ID": correlation,
        "X-Trace-ID": trace,
    }
    if error.http_status == 401:
        headers["WWW-Authenticate"] = "Bearer"
    retry_after = error.details.get("retryAfterSeconds")
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    ERROR_RESPONSES.labels(error.code, str(error.http_status)).inc()
    return JSONResponse(
        status_code=error.http_status,
        headers=headers,
        content={
            "correlationId": correlation,
            "traceId": trace,
            "error": {
                "code": error.code,
                "message": error.message,
                "retryable": error.retryable,
                "details": error.details,
            },
        },
    )


def install_error_handlers(application: FastAPI) -> None:
    @application.exception_handler(IdentityError)
    async def identity_error(request: Request, exc: IdentityError) -> JSONResponse:
        return _error_response(request, exc)

    @application.exception_handler(RequestValidationError)
    async def validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "location": ".".join(str(item) for item in error["loc"]),
                "type": error["type"],
            }
            for error in exc.errors()
        ]
        return _error_response(
            request,
            IdentityError(
                "INVALID_REQUEST",
                "Request validation failed",
                422,
                details={"violations": details},
            ),
        )

    @application.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
        LOGGER.error(
            "Database operation failed",
            extra={"errorCode": "DEPENDENCY_UNAVAILABLE"},
            exc_info=(type(exc), exc, exc.__traceback__),
        )
        return _error_response(request, DependencyUnavailable())

    @application.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        LOGGER.exception(
            "Unhandled Identity error",
            extra={"errorCode": "INTERNAL_ERROR"},
        )
        return _error_response(
            request,
            IdentityError("INTERNAL_ERROR", "An internal error occurred", 500),
        )
