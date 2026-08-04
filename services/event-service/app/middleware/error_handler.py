"""Chuan hoa loi domain thanh HTTP response dung format ErrorResponse
trong OpenAPI Giai doan 5: {correlationId, traceId?, error:{code,
message, retryable, details?}}."""

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.exceptions import (
    EventNotFoundError,
    IdempotencyKeyReusedError,
    InvalidEventDataError,
    InvalidStateTransitionError,
    VersionConflictError,
)


def _envelope(
    request: Request,
    code: str,
    message: str,
    retryable: bool,
    details: dict | None = None,
) -> dict:
    return {
        "correlationId": getattr(request.state, "correlation_id", None) or "unknown",
        "traceId": None,
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "details": details,
        },
    }


async def event_not_found_handler(request: Request, exc: EventNotFoundError):
    return JSONResponse(
        status_code=404, content=_envelope(request, exc.code, str(exc), False)
    )


async def invalid_transition_handler(
    request: Request, exc: InvalidStateTransitionError
):
    return JSONResponse(
        status_code=409,
        content=_envelope(
            request,
            exc.code,
            str(exc),
            False,
            {"current": exc.current, "target": exc.target},
        ),
    )


async def version_conflict_handler(request: Request, exc: VersionConflictError):
    return JSONResponse(
        status_code=409,
        content=_envelope(
            request,
            exc.code,
            str(exc),
            True,
            {"expected": exc.expected, "actual": exc.actual},
        ),
    )


async def invalid_data_handler(request: Request, exc: InvalidEventDataError):
    return JSONResponse(
        status_code=422, content=_envelope(request, exc.code, str(exc), False)
    )


async def idempotency_reused_handler(request: Request, exc: IdempotencyKeyReusedError):
    return JSONResponse(
        status_code=409, content=_envelope(request, exc.code, str(exc), False)
    )


async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Loi validate cua FastAPI/Pydantic (body/header sai kieu) -> cung
    format ErrorResponse thay vi default {"detail": [...]} cua FastAPI."""
    return JSONResponse(
        status_code=422,
        content=_envelope(
            request,
            "INVALID_EVENT_DATA",
            "Du lieu request khong hop le",
            False,
            {"errors": jsonable_encoder(exc.errors())},
        ),
    )
