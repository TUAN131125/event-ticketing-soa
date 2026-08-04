"""Quy tac chuyen trang thai (state machine), optimistic concurrency va
validation ngay/gio - EVT-07/08/09 va invariant #4 trong dac ta Giai
doan 3 (moi mutation dung resourceVersion/If-Match)."""

from datetime import datetime

from app.domain.enums import EventStatus
from app.domain.exceptions import (
    InvalidEventDataError,
    InvalidStateTransitionError,
    VersionConflictError,
)

ALLOWED_TRANSITIONS: dict[EventStatus, set[EventStatus]] = {
    EventStatus.DRAFT: {EventStatus.ON_SALE, EventStatus.CANCELLED},
    EventStatus.ON_SALE: {EventStatus.PAUSED, EventStatus.CANCELLED},
    EventStatus.PAUSED: {EventStatus.ON_SALE, EventStatus.CANCELLED},
    EventStatus.CANCELLED: set(),
    EventStatus.ENDED: set(),
}


def ensure_transition_allowed(current: EventStatus, target: EventStatus) -> None:
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidStateTransitionError(current.value, target.value)


def ensure_version_matches(expected: int, actual: int) -> None:
    """If-Match: client phai gui dung resourceVersion hien tai, tranh lost
    update khi 2 admin sua cung luc (invariant #4)."""
    if expected != actual:
        raise VersionConflictError(expected, actual)


def validate_event_dates(
    starts_at: datetime, sale_starts_at: datetime, sale_ends_at: datetime
) -> None:
    """422 INVALID_EVENT_DATA neu ngay gio khong hop ly."""
    if sale_starts_at >= sale_ends_at:
        raise InvalidEventDataError("saleStartsAt phai truoc saleEndsAt")
    if sale_ends_at > starts_at:
        raise InvalidEventDataError("saleEndsAt phai truoc hoac bang startsAt")


def compute_sale_eligibility(
    status: EventStatus, sale_starts_at: datetime, sale_ends_at: datetime, now: datetime
) -> tuple[bool, str | None]:
    """EVT-10: ESB goi truoc booking de biet co duoc dat ve khong.

    Invariant #1: chi ON_SALE va trong sale window moi duoc booking.
    """
    if status != EventStatus.ON_SALE:
        return False, f"EVENT_NOT_ON_SALE_STATUS_{status.value}"
    if now < sale_starts_at:
        return False, "SALE_NOT_STARTED"
    if now > sale_ends_at:
        return False, "SALE_ENDED"
    return True, None
