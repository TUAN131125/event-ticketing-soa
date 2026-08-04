"""Chuan hoa loi domain thanh HTTP response - dung dang o main.py qua
app.add_exception_handler(...). Dinh dang response khop dung schema
ErrorResponse trong contracts/openapi/customer-service.yaml:
{correlationId, traceId, error: {code, message, retryable}} - KHONG con
dung dang cu {"error": "TEXT", "detail": "..."} nhu truoc, vi sai contract."""
from fastapi import Request
from fastapi.responses import JSONResponse

from app.domain.exceptions import (
    CustomerNotFoundError,
    DuplicateEmailError,
    InvalidIfMatchError,
    VersionConflictError,
)


def _error_body(request: Request, code: str, message: str, retryable: bool) -> dict:
    return {
        "correlationId": getattr(request.state, "correlation_id", None),
        "traceId": None,
        "error": {"code": code, "message": message, "retryable": retryable},
    }


async def customer_not_found_handler(request: Request, exc: CustomerNotFoundError):
    return JSONResponse(
        status_code=404,
        content=_error_body(request, "CUSTOMER_NOT_FOUND", str(exc), retryable=False),
    )


async def duplicate_email_handler(request: Request, exc: DuplicateEmailError):
    return JSONResponse(
        status_code=409,
        content=_error_body(request, "DUPLICATE_EMAIL", str(exc), retryable=False),
    )


async def version_conflict_handler(request: Request, exc: VersionConflictError):
    # retryable=True: client co the doc lai resourceVersion moi nhat va
    # thu lai voi If-Match dung, khac voi DUPLICATE_EMAIL la loi nghiep vu
    # se khong tu het neu thu lai y het.
    return JSONResponse(
        status_code=409,
        content=_error_body(request, "VERSION_CONFLICT", str(exc), retryable=True),
    )


async def invalid_if_match_handler(request: Request, exc: InvalidIfMatchError):
    return JSONResponse(
        status_code=422,
        content=_error_body(request, "INVALID_IF_MATCH", str(exc), retryable=False),
    )
