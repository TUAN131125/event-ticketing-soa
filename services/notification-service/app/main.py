"""Diem khoi dong Notification Service.

Chay doc lap: uvicorn app.main:app --host 0.0.0.0 --port 8007
"""
from fastapi import FastAPI

from app.api.router import api_router
from app.middleware.correlation_id import CorrelationIdMiddleware
from app.middleware.logging import RequestLoggingMiddleware

app = FastAPI(title="Notification Service", version="1.0.0")

app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(CorrelationIdMiddleware)

app.include_router(api_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8007, reload=True)
