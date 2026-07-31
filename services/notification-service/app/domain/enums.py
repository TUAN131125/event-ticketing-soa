"""Cac enum thuoc domain cua Notification Service."""
from enum import Enum


class NotificationType(str, Enum):
    BOOKING_CONFIRMED = "booking.confirmed"
    BOOKING_FAILED = "booking.failed"
    EVENT_CHANGED = "event.changed"


class DeliveryStatus(str, Enum):
    SENT = "SENT"
    FAILED = "FAILED"
