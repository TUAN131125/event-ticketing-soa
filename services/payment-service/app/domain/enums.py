"""Payment aggregate enumerations.

Existing public values are kept. New values extend the Stage 3/5 payment state
model without renaming any value already consumed by the orchestrator.
"""

from enum import StrEnum


class PaymentStatus(StrEnum):
    PENDING = "PENDING"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    UNKNOWN = "UNKNOWN"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"


class ReconciliationStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ProviderOperation(StrEnum):
    AUTHORIZE = "AUTHORIZE"
    CAPTURE = "CAPTURE"
    CANCEL = "CANCEL"
    REFUND = "REFUND"


class ProviderOutcomeSource(StrEnum):
    COMMAND = "COMMAND"
    CALLBACK = "CALLBACK"
    RECONCILIATION = "RECONCILIATION"
    MOCK_PROVIDER = "MOCK_PROVIDER"


class MockProviderScenario(StrEnum):
    MANUAL = "MANUAL"
    SUCCESS = "SUCCESS"
    DECLINE = "DECLINE"
    TIMEOUT = "TIMEOUT"


class RefundKind(StrEnum):
    REQUESTED = "REQUESTED"
    RECONCILIATION = "RECONCILIATION"


class PaymentEventType(StrEnum):
    CREATED = "payment.created"
    AUTHORIZED = "payment.authorized"
    SUCCEEDED = "payment.succeeded"
    UNKNOWN = "payment.unknown"
    FAILED = "payment.failed"
    CANCELLED = "payment.cancelled"
    REFUNDED = "payment.refunded"
    RECONCILED = "payment.reconciled"
