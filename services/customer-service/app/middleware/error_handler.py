"""Chuan hoa loi domain thanh HTTP response - dung dang o main.py qua
app.add_exception_handler(...)."""
from fastapi import Request
from fastapi.responses import JSONResponse

from app.domain.exceptions import CustomerNotFoundError, DuplicateEmailError


async def customer_not_found_handler(request: Request, exc: CustomerNotFoundError):
    return JSONResponse(
        status_code=404,
        content={
            "error": "CUSTOMER_NOT_FOUND",
            "detail": str(exc),
            "correlationId": getattr(request.state, "correlation_id", None),
        },
    )


async def duplicate_email_handler(request: Request, exc: DuplicateEmailError):
    return JSONResponse(
        status_code=409,
        content={
            "error": "DUPLICATE_EMAIL",
            "detail": str(exc),
            "correlationId": getattr(request.state, "correlation_id", None),
        },
    )
