"""Booking aggregate enumerations.

The values in this module are the persisted/public contract values.  Existing
values are never renamed; new values extend the state machine defined in the
Stage 5 contract.
"""

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
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"


class ReservationEvidenceStatus(StrEnum):
    PENDING = "PENDING"
    RESERVED = "RESERVED"
    CONFIRMED = "CONFIRMED"
    RELEASE_PENDING = "RELEASE_PENDING"
    RELEASED = "RELEASED"
    UNKNOWN = "UNKNOWN"


class CompensationStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CompensationAction(StrEnum):
    NONE = "NONE"
    RELEASE_RESERVATION = "RELEASE_RESERVATION"
    REFUND_PAYMENT = "REFUND_PAYMENT"
    RELEASE_AND_REFUND = "RELEASE_AND_REFUND"
    RECONCILE_PAYMENT = "RECONCILE_PAYMENT"


class RecoveryAction(StrEnum):
    ATTACH_RESERVATION = "ATTACH_RESERVATION"
    START_PAYMENT = "START_PAYMENT"
    QUERY_PAYMENT = "QUERY_PAYMENT"
    RECONCILE_PAYMENT = "RECONCILE_PAYMENT"
    RELEASE_RESERVATION_AND_FAIL = "RELEASE_RESERVATION_AND_FAIL"
    CONFIRM_RESERVATION = "CONFIRM_RESERVATION"
    ISSUE_TICKETS = "ISSUE_TICKETS"
    CONFIRM_BOOKING = "CONFIRM_BOOKING"
    COMPLETE_COMPENSATION = "COMPLETE_COMPENSATION"
    NO_ACTION = "NO_ACTION"


class BookingEventType(StrEnum):
    CREATED = "booking.created"
    CONFIRMED = "booking.confirmed"
    FAILED = "booking.failed"
    CANCELLED = "booking.cancelled"
