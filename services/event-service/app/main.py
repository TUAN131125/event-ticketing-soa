"""Diem khoi dong Event Service.

Chay doc lap: uvicorn app.main:app --host 0.0.0.0 --port 8002
"""
from fastapi import FastAPI

from app.api.router import api_router
from app.domain.exceptions import EventNotFoundError, InvalidStateTransitionError
from app.middleware.correlation_id import CorrelationIdMiddleware
from app.middleware.error_handler import (
    event_not_found_handler,
    invalid_transition_handler,
)
from app.middleware.logging import RequestLoggingMiddleware

app = FastAPI(title="Event Service", version="1.0.0")

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CorrelationIdMiddleware)

app.add_exception_handler(EventNotFoundError, event_not_found_handler)
app.add_exception_handler(InvalidStateTransitionError, invalid_transition_handler)

app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8002, reload=True)
