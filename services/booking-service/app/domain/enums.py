"""Booking aggregate enumerations."""

from enum import StrEnum


class BookingStatus(StrEnum):
    PENDING = "PENDING"
    SEAT_RESERVED = "SEAT_RESERVED"
    PAYMENT_PROCESSING = "PAYMENT_PROCESSING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    COMPENSATION_PENDING = "COMPENSATION_PENDING"


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class BookingEventType(StrEnum):
    CREATED = "booking.created"
    CONFIRMED = "booking.confirmed"
    FAILED = "booking.failed"
    CANCELLED = "booking.cancelled"
