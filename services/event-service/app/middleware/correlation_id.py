"""Middleware gan Correlation ID cho moi request (giu nguyen neu ESB da gui)."""
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    HEADER = "X-Correlation-Id"

    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get(self.HEADER) or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers[self.HEADER] = correlation_id
        return response
