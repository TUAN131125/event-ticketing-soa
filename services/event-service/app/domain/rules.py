"""Quy tac chuyen trang thai su kien (state machine)."""

from app.domain.enums import EventStatus
from app.domain.exceptions import InvalidStateTransitionError

ALLOWED_TRANSITIONS: dict[EventStatus, set[EventStatus]] = {
    EventStatus.DRAFT: {EventStatus.ON_SALE, EventStatus.CANCELLED},
    EventStatus.ON_SALE: {
        EventStatus.PAUSED,
        EventStatus.ENDED,
        EventStatus.CANCELLED,
    },
    EventStatus.PAUSED: {
        EventStatus.ON_SALE,
        EventStatus.ENDED,
        EventStatus.CANCELLED,
    },
    EventStatus.ENDED: set(),
    EventStatus.CANCELLED: set(),
}


def ensure_transition_allowed(current: EventStatus, target: EventStatus) -> None:
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise InvalidStateTransitionError(current.value, target.value)
