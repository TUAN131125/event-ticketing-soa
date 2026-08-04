"""Bat toan bo loi domain (va loi validate cua Pydantic/FastAPI) roi dich
thanh ErrorResponse dung dinh dang hop dong (Giai doan 5):
{correlationId, traceId, error:{code, message, retryable, details?}}.

Day la NOI DUY NHAT quyet dinh khuon dang loi tra ve cho client - use
case/domain chi can nem dung exception (app/domain/exceptions.py), khong
tu build JSONResponse."""
from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.exceptions import NotificationDomainError


def _correlation_id(request: Request) -> str:
    correlation_id = getattr(request.state, "correlation_id", None)
    return correlation_id or "unknown-correlation-id"


async def domain_error_handler(request: Request, exc: NotificationDomainError) -> JSONResponse:
    body: dict = {
        "correlationId": _correlation_id(request),
        "traceId": None,
        "error": {
            "code": exc.code,
            "message": exc.message,
            "retryable": exc.retryable,
        },
    }
    if exc.details:
        body["error"]["details"] = exc.details
    return JSONResponse(status_code=exc.http_status, content=body)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "correlationId": _correlation_id(request),
            "traceId": None,
            "error": {
                "code": "EVENT_SCHEMA_INVALID",
                "message": "Payload khong hop le theo schema",
                "retryable": False,
                "details": {"errors": exc.errors()},
            },
        },
    )
