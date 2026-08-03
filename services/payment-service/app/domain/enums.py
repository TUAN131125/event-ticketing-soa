"""Payment aggregate enumerations."""

from enum import StrEnum


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"


class RefundKind(StrEnum):
    REQUESTED = "REQUESTED"
    RECONCILIATION = "RECONCILIATION"


class PaymentEventType(StrEnum):
    CREATED = "payment.created"
    AUTHORIZED = "payment.authorized"
    SUCCEEDED = "payment.succeeded"
    FAILED = "payment.failed"
    CANCELLED = "payment.cancelled"
    REFUNDED = "payment.refunded"
