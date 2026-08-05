"""Canonical Notification delivery enums."""

from enum import StrEnum


class DeliveryStatus(StrEnum):
    PENDING = "PENDING"
    SENDING = "SENDING"
    DELIVERED = "DELIVERED"
    RETRY_PENDING = "RETRY_PENDING"
    DEAD_LETTER = "DEAD_LETTER"
    CANCELLED = "CANCELLED"
