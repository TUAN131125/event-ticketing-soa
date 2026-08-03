"""Booking aggregate enumerations."""

from enum import StrEnum


class BookingStatus(StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class BookingEventType(StrEnum):
    CREATED = "booking.created"
    CONFIRMED = "booking.confirmed"
    FAILED = "booking.failed"
    CANCELLED = "booking.cancelled"
