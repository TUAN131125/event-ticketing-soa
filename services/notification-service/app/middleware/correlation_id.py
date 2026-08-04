"""Middleware gan Correlation ID cho moi request.

Ten header khop tham so `CorrelationId` trong hop dong (Giai doan 5,
contracts/openapi/notification-service.yaml): X-Correlation-ID.

Neu ESB/webhook payload da co correlationId rieng trong EventEnvelope
(NOT bang header nay) - day la Correlation ID o muc HTTP request (dung
de trace log/error response), doc lap voi correlationId nghiep vu trong
envelope.
"""
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    HEADER = "X-Correlation-ID"

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get(self.HEADER) or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers[self.HEADER] = correlation_id
        return response
