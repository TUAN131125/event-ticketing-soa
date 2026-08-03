"""Stable domain errors exposed by Payment Service."""

from __future__ import annotations

from typing import Any


class PaymentError(Exception):
    code = "PAYMENT_ERROR"
    http_status = 400
    retryable = False

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InvalidRequest(PaymentError):
    code = "INVALID_REQUEST"


class AuthenticationFailed(PaymentError):
    code = "AUTHENTICATION_FAILED"
    http_status = 401

    def __init__(self) -> None:
        super().__init__("Internal service authentication failed")


class PaymentNotFound(PaymentError):
    code = "PAYMENT_NOT_FOUND"
    http_status = 404

    def __init__(self, payment_id: str) -> None:
        super().__init__(
            f"Payment {payment_id} was not found",
            details={"paymentId": payment_id},
        )


class InvalidStateTransition(PaymentError):
    code = "INVALID_STATE_TRANSITION"
    http_status = 409

    def __init__(self, current: str, target: str) -> None:
        super().__init__(
            f"Payment cannot transition from {current} to {target}",
            details={"currentStatus": current, "targetStatus": target},
        )


class VersionConflict(PaymentError):
    code = "VERSION_CONFLICT"
    http_status = 409

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(
            "Payment resource version does not match",
            details={"expectedVersion": expected, "actualVersion": actual},
        )


class IdempotencyConflict(PaymentError):
    code = "IDEMPOTENCY_CONFLICT"
    http_status = 409

    def __init__(self) -> None:
        super().__init__("Idempotency key was already used for another request")


class BookingPaymentConflict(PaymentError):
    code = "BOOKING_PAYMENT_CONFLICT"
    http_status = 409

    def __init__(self, booking_id: str) -> None:
        super().__init__(
            f"Booking {booking_id} is already attached to another payment definition",
            details={"bookingId": booking_id},
        )


class ProviderReferenceConflict(PaymentError):
    code = "PROVIDER_REFERENCE_CONFLICT"
    http_status = 409

    def __init__(self) -> None:
        super().__init__("Provider reference does not match the payment")


class DependencyUnavailable(PaymentError):
    code = "DEPENDENCY_UNAVAILABLE"
    http_status = 503
    retryable = True

    def __init__(self) -> None:
        super().__init__("Payment persistence is temporarily unavailable")


class InternalFailure(PaymentError):
    code = "INTERNAL_ERROR"
    http_status = 500

    def __init__(self) -> None:
        super().__init__("Payment Service could not complete the request")
