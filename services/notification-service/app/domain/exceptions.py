"""Loi thuoc domain - khong phu thuoc HTTP status code.

Moi exception mang theo 1 error code CHUAN theo Muc 6 "Ma loi va xu ly
that bai" cua dac ta SVC-08, de middleware/error_handler.py dich thanh
ErrorResponse{correlationId, traceId, error:{code, message, retryable}}
dung dinh dang hop dong (Giai doan 5).
"""
from __future__ import annotations


class NotificationDomainError(Exception):
    code: str = "INTERNAL_ERROR"
    http_status: int = 500
    retryable: bool = False

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class WebhookSignatureInvalidError(NotificationDomainError):
    code = "WEBHOOK_SIGNATURE_INVALID"
    http_status = 401
    retryable = False


class EventSchemaInvalidError(NotificationDomainError):
    code = "EVENT_SCHEMA_INVALID"
    http_status = 422
    retryable = False


class DuplicateEventError(NotificationDomainError):
    code = "DUPLICATE_EVENT"
    http_status = 409
    retryable = False

    def __init__(self, event_id: str) -> None:
        super().__init__(f"Da xu ly eventId nay roi: {event_id}")
        self.event_id = event_id


class DeliveryNotFoundError(NotificationDomainError):
    code = "DELIVERY_NOT_FOUND"
    http_status = 404
    retryable = False

    def __init__(self, delivery_id: str) -> None:
        super().__init__(f"Khong tim thay delivery: {delivery_id}")
        self.delivery_id = delivery_id


class DeliveryNotRetryableError(NotificationDomainError):
    """Retry thu cong vao delivery dang o trang thai khong cho phep (vd
    da DELIVERED hoac CANCELLED) - xung dot voi trang thai hien tai."""

    code = "DELIVERY_NOT_RETRYABLE"
    http_status = 409
    retryable = False

    def __init__(self, delivery_id: str, current_status: str) -> None:
        super().__init__(
            f"Delivery {delivery_id} dang o trang thai {current_status}, khong the retry"
        )
        self.delivery_id = delivery_id
        self.current_status = current_status


class TemplateNotFoundError(NotificationDomainError):
    code = "TEMPLATE_NOT_FOUND"
    http_status = 404
    retryable = False

    def __init__(self, template_code: str) -> None:
        super().__init__(f"Khong tim thay template: {template_code}")
        self.template_code = template_code


class TemplateVersionConflictError(NotificationDomainError):
    """If-Match khong khop resource_version hien tai - optimistic
    concurrency conflict (giong ETag)."""

    code = "TEMPLATE_VERSION_CONFLICT"
    http_status = 409
    retryable = False

    def __init__(self, template_code: str, expected: str, actual: int) -> None:
        super().__init__(
            f"If-Match={expected} khong khop resource_version hien tai ({actual})"
            f" cua template {template_code}"
        )
        self.template_code = template_code


class ProviderTemporaryError(NotificationDomainError):
    code = "PROVIDER_TEMPORARY_ERROR"
    http_status = 503
    retryable = True


class ProviderPermanentError(NotificationDomainError):
    code = "PROVIDER_PERMANENT_ERROR"
    http_status = 422
    retryable = False
