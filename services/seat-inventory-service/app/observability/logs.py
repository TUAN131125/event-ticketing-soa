"""JSON structured logging without request bodies or secrets."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.observability.tracing import get_correlation_id


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "service": "seat-inventory-service",
            "logger": record.name,
            "correlationId": get_correlation_id(),
            "message": record.getMessage(),
        }
        for key in (
            "operation",
            "event_id",
            "booking_id",
            "reservation_id",
            "seat_count",
            "result",
            "error_code",
            "duration_ms",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def operation_log_fields(operation: str, **values: object) -> dict[str, object]:
    return {"operation": operation, **values}
