"""Exception handlers that never expose internals."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.domain.exceptions import DependencyUnavailable, IdentityError
from app.observability.metrics import AUTH_EVENTS

LOGGER = logging.getLogger(__name__)


def _ids(request: Request) -> tuple[str, str]:
    context = getattr(request.state, "identity_context", None)
    if context is None:
        return "-", "-"
    return context.correlation_id, context.trace_id


def _response(request: Request, error: IdentityError) -> JSONResponse:
    correlation, trace = _ids(request)
    headers: dict[str, str] = {}
    if error.http_status == 401:
        headers["WWW-Authenticate"] = "Bearer"
    retry_after = error.details.get("retryAfterSeconds")
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
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
        AUTH_EVENTS.labels(exc.code, "failure").inc()
        return _response(request, exc)

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
        return _response(
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
            "Database operation failed", extra={"errorCode": "DEPENDENCY_UNAVAILABLE"}
        )
        return _response(request, DependencyUnavailable())

    @application.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        LOGGER.exception(
            "Unhandled Identity error", extra={"errorCode": "INTERNAL_ERROR"}
        )
        return _response(
            request, IdentityError("INTERNAL_ERROR", "An internal error occurred", 500)
        )
