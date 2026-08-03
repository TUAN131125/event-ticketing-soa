"""Correlation-ID propagation middleware."""

from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from fastapi import Request, Response

from app.security.input_validation import safe_identifier

_correlation_id: ContextVar[str] = ContextVar("ticket_correlation_id", default="")


async def correlation_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    correlation_id = safe_identifier(request.headers.get("X-Correlation-ID"))
    request.state.correlation_id = correlation_id
    token = _correlation_id.set(correlation_id)
    try:
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response
    finally:
        _correlation_id.reset(token)


def current_correlation_id() -> str:
    return _correlation_id.get() or "unknown"
