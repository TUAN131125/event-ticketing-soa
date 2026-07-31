"""Diem khoi dong Customer Service.

Chay doc lap: uvicorn app.main:app --host 0.0.0.0 --port 8001
"""
from fastapi import FastAPI

from app.api.router import api_router
from app.domain.exceptions import CustomerNotFoundError, DuplicateEmailError
from app.middleware.correlation_id import CorrelationIdMiddleware
from app.middleware.error_handler import (
    customer_not_found_handler,
    duplicate_email_handler,
)
from app.middleware.logging import RequestLoggingMiddleware

app = FastAPI(title="Customer Service", version="1.0.0")

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CorrelationIdMiddleware)

app.add_exception_handler(CustomerNotFoundError, customer_not_found_handler)
app.add_exception_handler(DuplicateEmailError, duplicate_email_handler)

app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, reload=True)
