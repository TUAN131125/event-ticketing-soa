"""Enum trang thai su kien."""

from enum import StrEnum


class EventStatus(StrEnum):
    DRAFT = "DRAFT"
    ON_SALE = "ON_SALE"
    PAUSED = "PAUSED"
    ENDED = "ENDED"
    CANCELLED = "CANCELLED"
