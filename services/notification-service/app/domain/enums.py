"""Cac enum thuoc domain, khop dung enum trong OpenAPI (Delivery.status,
Delivery.channel) va SQL baseline (Giai doan 5)."""
from enum import Enum


class EventType(str, Enum):
    BOOKING_CONFIRMED = "booking.confirmed"
    BOOKING_FAILED = "booking.failed"
    EVENT_CHANGED = "event.changed"
    TICKET_ISSUED = "ticket.issued"


class Channel(str, Enum):
    EMAIL = "EMAIL"
    SMS = "SMS"


class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    SENDING = "SENDING"
    DELIVERED = "DELIVERED"
    RETRY_PENDING = "RETRY_PENDING"
    DEAD_LETTER = "DEAD_LETTER"
    CANCELLED = "CANCELLED"


# Trang thai duoc phep goi retry thu cong (NOT-05/NOT-08). DELIVERED va
# CANCELLED la trang thai ket thuc (terminal) - retry vao day phai tra 409.
RETRYABLE_STATUSES = frozenset({DeliveryStatus.RETRY_PENDING, DeliveryStatus.DEAD_LETTER})
