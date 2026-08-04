"""Quy tac nghiep vu thuan cua Notification Service (Muc 4.2 dac ta
SVC-08: "eventId duy nhat bao dam consumer idempotency", "Retry chi cho
loi transient", "Template version luu cung delivery evidence")."""
from __future__ import annotations

from app.domain.entities import Delivery, Template
from app.domain.enums import RETRYABLE_STATUSES
from app.domain.exceptions import (
    DeliveryNotRetryableError,
    DuplicateEventError,
    TemplateVersionConflictError,
)

# NOT-06: DeadLetter - so lan thu toi da truoc khi chuyen DEAD_LETTER.
MAX_DELIVERY_ATTEMPTS = 5
# Backoff co so (giay) cho exponential backoff: base * 2^(attempt-1).
RETRY_BACKOFF_BASE_SECONDS = 30


def ensure_event_not_duplicate(already_exists: bool, event_id: str) -> None:
    """eventId la hang rao idempotency chinh cua ca service (Muc 4.2)."""
    if already_exists:
        raise DuplicateEventError(event_id)


def ensure_delivery_retryable(delivery: Delivery) -> None:
    """Chi cho retry thu cong (NOT-05/NOT-08) khi delivery dang
    RETRY_PENDING hoac DEAD_LETTER - DELIVERED/CANCELLED la trang thai
    ket thuc, SENDING/PENDING dang duoc xu ly, retry vao day la xung dot
    trang thai (409), khong phai loi nguoi dung."""
    if delivery.status not in RETRYABLE_STATUSES:
        raise DeliveryNotRetryableError(delivery.id, delivery.status.value)


def ensure_template_version_matches(template: Template, if_match: str) -> None:
    """If-Match phai la resource_version hien tai, dinh dang \"<so>\"
    (giong ETag) - dam bao optimistic concurrency khi 2 admin cung sua 1
    template."""
    try:
        expected_version = int(if_match.strip('"'))
    except ValueError as exc:
        raise TemplateVersionConflictError(template.code, if_match, template.resource_version) from exc
    if expected_version != template.resource_version:
        raise TemplateVersionConflictError(template.code, if_match, template.resource_version)
