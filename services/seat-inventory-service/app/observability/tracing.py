"""Correlation context propagated through logs and SOAP responses."""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar, Token

_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")
_SAFE_CORRELATION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def new_correlation_id() -> str:
    return str(uuid.uuid4())


def sanitize_correlation_id(value: str | None) -> str:
    if value and _SAFE_CORRELATION.fullmatch(value):
        return value
    return new_correlation_id()


def set_correlation_id(value: str) -> Token[str]:
    return _correlation_id.set(sanitize_correlation_id(value))


def reset_correlation_id(token: Token[str]) -> None:
    _correlation_id.reset(token)


def get_correlation_id() -> str:
    return _correlation_id.get()
