from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

SENSITIVE = {
    "authorization",
    "cookie",
    "token",
    "ticket",
    "paymentMethodToken",
    "email",
    "phone",
    "secret",
}


def redact(value: Any, key: str = "") -> Any:
    if any(word.lower() in key.lower() for word in SENSITIVE):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(k): redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "service": "booking-orchestrator",
            "level": record.levelname,
            "message": record.getMessage(),
        }
        for name in (
            "correlationId",
            "traceId",
            "workflowId",
            "operation",
            "provider",
            "step",
            "outcome",
            "duration",
        ):
            value = getattr(record, name, None)
            if value is not None:
                data[name] = value
        return json.dumps(redact(data), separators=(",", ":"), default=str)


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
