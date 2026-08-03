"""Structured JSON logs with an explicit safe-field allow-list."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from app.observability.tracing import current_correlation_id, current_trace_id

SAFE_FIELDS = {
    "operation",
    "outcome",
    "durationMs",
    "status",
    "reason",
    "activeConnections",
    "bookingRef",
    "errorCode",
    "correlationId",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": "realtime-status-service",
            "message": record.getMessage(),
            "correlationId": current_correlation_id(),
            "traceId": current_trace_id(),
        }
        for name in SAFE_FIELDS:
            if hasattr(record, name):
                payload[name] = getattr(record, name)
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
    logging.getLogger("httpx").setLevel(logging.WARNING)
