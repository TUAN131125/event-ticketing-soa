"""Loi thuoc domain cua Event Service - moi loi map sang 1 HTTP status +
error code trong ErrorResponse.error.code (xem middleware/error_handler.py)."""


class EventNotFoundError(Exception):
    code = "EVENT_NOT_FOUND"

    def __init__(self, event_id: str):
        self.event_id = event_id
        super().__init__(f"Khong tim thay su kien: {event_id}")


class InvalidStateTransitionError(Exception):
    code = "INVALID_EVENT_TRANSITION"

    def __init__(self, current: str, target: str):
        self.current = current
        self.target = target
        super().__init__(f"Khong the chuyen tu {current} sang {target}")


class VersionConflictError(Exception):
    code = "VERSION_CONFLICT"

    def __init__(self, expected: int, actual: int):
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"If-Match khong khop: client gui {expected}, hien tai la {actual}"
        )


class InvalidEventDataError(Exception):
    code = "INVALID_EVENT_DATA"

    def __init__(self, message: str):
        super().__init__(message)


class IdempotencyKeyReusedError(Exception):
    """Cung Idempotency-Key nhung than request khac - khach hang dung sai
    key (phai la 1 key rieng cho moi request logic khac nhau)."""

    code = "IDEMPOTENCY_KEY_REUSED"

    def __init__(self, key: str):
        self.key = key
        super().__init__(f"Idempotency-Key '{key}' da dung cho request khac truoc do")
