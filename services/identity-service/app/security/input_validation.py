"""Validation and sanitization for untrusted transport metadata."""

from __future__ import annotations

import re
import uuid

_CORRELATION = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_TRACEPARENT = re.compile(
    r"^[\da-f]{2}-([\da-f]{32})-([\da-f]{16})-[\da-f]{2}$", re.IGNORECASE
)


def correlation_id(value: str | None) -> str:
    if value and _CORRELATION.fullmatch(value):
        return value
    return str(uuid.uuid4())


def trace_id(value: str | None) -> str:
    if value:
        match = _TRACEPARENT.fullmatch(value.strip())
        if match and match.group(1) != "0" * 32:
            return match.group(1).lower()
    return uuid.uuid4().hex


def bounded_user_agent(value: str | None) -> str | None:
    if value is None:
        return None
    sanitized = "".join(character for character in value if character.isprintable())
    return sanitized[:512]
