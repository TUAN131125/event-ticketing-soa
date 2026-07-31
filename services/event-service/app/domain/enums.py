"""Enum trang thai su kien."""
from enum import Enum


class EventStatus(str, Enum):
    DRAFT = "DRAFT"
    ON_SALE = "ON_SALE"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
