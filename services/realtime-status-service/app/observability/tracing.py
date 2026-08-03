"""Small context-variable bridge for correlation and trace identifiers."""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar, Token

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_correlation: ContextVar[str] = ContextVar("realtime_correlation", default="unknown")
_trace: ContextVar[str] = ContextVar("realtime_trace", default="unknown")


def safe_id(value: str | None) -> str:
    if value and SAFE_ID.fullmatch(value.strip()):
        return value.strip()
    return str(uuid.uuid4())


def trace_id(traceparent: str | None) -> str:
    if traceparent:
        parts = traceparent.split("-")
        if (
            len(parts) == 4
            and len(parts[1]) == 32
            and all(char in "0123456789abcdef" for char in parts[1].lower())
        ):
            return parts[1].lower()
    return uuid.uuid4().hex


def bind(correlation_id: str, trace: str) -> tuple[Token[str], Token[str]]:
    return _correlation.set(correlation_id), _trace.set(trace)


def reset(tokens: tuple[Token[str], Token[str]]) -> None:
    _correlation.reset(tokens[0])
    _trace.reset(tokens[1])


def current_correlation_id() -> str:
    return _correlation.get()


def current_trace_id() -> str:
    return _trace.get()
