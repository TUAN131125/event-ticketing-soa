"""Safe request metadata normalization."""

import re
import uuid

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


def safe_identifier(value: str | None, *, fallback: str | None = None) -> str:
    if value:
        normalized = value.strip()
        if SAFE_ID.fullmatch(normalized):
            return normalized
    return fallback or str(uuid.uuid4())
