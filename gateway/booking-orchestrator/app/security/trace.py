from __future__ import annotations

import re
import secrets

TRACEPARENT = re.compile(
    r"^[\da-f]{2}-([\da-f]{32})-([\da-f]{16})-[\da-f]{2}$",
    re.IGNORECASE,
)


def parse_trace_id(value: str | None) -> str:
    """Extract a valid W3C trace id or create a new non-zero 128-bit id."""

    if value:
        match = TRACEPARENT.match(value.strip())
        if match and match.group(1) != "0" * 32:
            return match.group(1).lower()
    return secrets.token_hex(16)
