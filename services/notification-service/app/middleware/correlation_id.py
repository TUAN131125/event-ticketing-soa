"""Middleware gan Correlation ID cho moi request.

Neu ESB/webhook payload da co correlationId rieng trong body thi khong
lien quan header nay - day la Correlation ID o muc HTTP request (dung de
trace log giua cac middleware/observability), doc lap voi correlationId
nghiep vu trong payload webhook.
"""

import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    HEADER = "X-Correlation-ID"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        correlation_id = request.headers.get(self.HEADER) or str(uuid.uuid4())
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers[self.HEADER] = correlation_id
        return response
