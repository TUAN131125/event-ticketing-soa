"""Safe request metadata normalization."""

import uuid

from app.domain.rules import IDENTIFIER


def safe_identifier(value: str | None, *, fallback: str | None = None) -> str:
    """Return the value when it is a safe identifier, otherwise a generated one.

    Request metadata such as X-Correlation-ID is caller supplied, so it has to
    satisfy the same identifier rule the domain enforces before it can reach a
    log line, an audit row or an error envelope.
    """
    if value:
        normalized = value.strip()
        if IDENTIFIER.fullmatch(normalized):
            return normalized
    return fallback or str(uuid.uuid4())
