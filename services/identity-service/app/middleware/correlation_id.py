"""Correlation, trace and safe request metadata middleware."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.domain.value_objects import RequestContext
from app.observability.tracing import bind, reset
from app.security.input_validation import bounded_user_agent, correlation_id, trace_id

MAX_REQUEST_BODY_BYTES = 64 * 1024


async def context_middleware(
    request: Request, call_next
):  # type: ignore[no-untyped-def]
    correlation = correlation_id(request.headers.get("X-Correlation-ID"))
    trace = trace_id(request.headers.get("traceparent"))
    client_ip = request.client.host if request.client else "unknown"
    request.state.identity_context = RequestContext(
        correlation_id=correlation,
        trace_id=trace,
        client_ip=client_ip,
        user_agent=bounded_user_agent(request.headers.get("User-Agent")),
    )
    tokens = bind(correlation, trace)
    try:
        content_length = request.headers.get("content-length")
        try:
            too_large = (
                content_length is not None
                and int(content_length) > MAX_REQUEST_BODY_BYTES
            )
        except ValueError:
            too_large = False
        if too_large:
            return JSONResponse(
                status_code=413,
                content={
                    "correlationId": correlation,
                    "traceId": trace,
                    "error": {
                        "code": "REQUEST_TOO_LARGE",
                        "message": "Request body exceeds the configured limit",
                        "retryable": False,
                        "details": {},
                    },
                },
                headers={"X-Correlation-ID": correlation, "X-Trace-ID": trace},
            )
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation
        response.headers["X-Trace-ID"] = trace
        return response
    finally:
        reset(tokens)
