"""Middleware gan Correlation ID cho moi request.

Neu ESB da gui header X-Correlation-Id thi giu nguyen (de trace xuyen suot
nhieu service); neu khong co (vd goi truc tiep luc test) thi tu sinh moi.
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
