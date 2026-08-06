from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(slots=True)
class EsbError(Exception):
    code: str
    message: str
    status_code: int = 400
    retryable: bool = False
    details: dict[str, Any] | None = None

    def __str__(self) -> str:
        return self.message

class DependencyError(EsbError):
    pass

class PaymentUnknown(EsbError):
    def __init__(self, message: str='Payment outcome is not yet authoritative'):
        super().__init__('PAYMENT_UNKNOWN', message, 202, True)

class Forbidden(EsbError):
    def __init__(self, message: str='Forbidden'):
        super().__init__('FORBIDDEN', message, 403, False)

class NotFound(EsbError):
    def __init__(self, resource: str):
        super().__init__('RESOURCE_NOT_FOUND', f'{resource} was not found', 404, False)

class Conflict(EsbError):
    def __init__(self, code: str, message: str):
        super().__init__(code, message, 409, False)
