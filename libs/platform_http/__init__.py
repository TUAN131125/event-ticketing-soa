"""Domain-free HTTP response helpers used by service boundaries."""

from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict
from starlette.requests import Request


class HealthStatus(BaseModel):
    """Domain-free health payload shared by HTTP service boundaries."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["UP", "READY", "NOT_READY"]
    service: str | None = None
    version: str | None = None


def parse_if_match(value: str) -> int:
    if len(value) < 3 or value[0] != '"' or value[-1] != '"':
        raise ValueError("If-Match must contain a quoted positive resource version")
    version = int(value[1:-1])
    if version < 1:
        raise ValueError("If-Match must contain a positive resource version")
    return version


def etag(version: int) -> str:
    return f'"{version}"'


def error_envelope(
    request: Request,
    *,
    code: str,
    message: str,
    retryable: bool = False,
    details: Any | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "correlationId": getattr(request.state, "correlation_id", uuid4().hex),
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
        },
    }
    trace_id = request.headers.get("traceparent")
    if trace_id:
        payload["traceId"] = trace_id
    if details is not None:
        payload["error"]["details"] = details
    return payload


__all__ = ["HealthStatus", "error_envelope", "etag", "parse_if_match"]
