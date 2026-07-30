"""Structured JSON logging without request bodies or credentials."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from app.observability.tracing import current_correlation_id, current_trace_id

_STANDARD = set(logging.makeLogRecord({}).__dict__)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": "identity-service",
            "message": record.getMessage(),
            "correlationId": current_correlation_id(),
            "traceId": current_trace_id(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD and key not in {"message", "asctime"}:
                payload[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = record.exc_info[0].__name__
        return json.dumps(payload, default=str, separators=(",", ":"))


def configure_logging(level: str) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    logging.getLogger("uvicorn.access").disabled = True
