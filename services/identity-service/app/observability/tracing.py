"""Request correlation context for logs."""

from __future__ import annotations

from contextvars import ContextVar, Token

_correlation: ContextVar[str] = ContextVar("correlation_id", default="-")
_trace: ContextVar[str] = ContextVar("trace_id", default="-")


def bind(correlation_id: str, trace_id: str) -> tuple[Token[str], Token[str]]:
    return _correlation.set(correlation_id), _trace.set(trace_id)


def reset(tokens: tuple[Token[str], Token[str]]) -> None:
    _correlation.reset(tokens[0])
    _trace.reset(tokens[1])


def current_correlation_id() -> str:
    return _correlation.get()


def current_trace_id() -> str:
    return _trace.get()
