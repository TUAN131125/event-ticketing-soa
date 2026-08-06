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


class ProviderSignatureInvalid(PaymentError):
    code = "PROVIDER_SIGNATURE_INVALID"
    http_status = 401

    def __init__(self, message: str = "Provider callback signature is invalid") -> None:
        super().__init__(message)


class PaymentNotFound(PaymentError):
    code = "PAYMENT_NOT_FOUND"
    http_status = 404

    def __init__(self, payment_id: str) -> None:
        super().__init__(
            f"Payment {payment_id} was not found",
            details={"paymentId": payment_id},
        )


class InvalidStateTransition(PaymentError):
    code = "INVALID_PAYMENT_TRANSITION"
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
    # Keep the established class while exposing the canonical contract code.
    code = "IDEMPOTENCY_KEY_REUSED"
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


class PaymentAmountMismatch(PaymentError):
    code = "PAYMENT_AMOUNT_MISMATCH"
    http_status = 409

    def __init__(
        self,
        *,
        expected_amount: str,
        actual_amount: str,
        expected_currency: str,
        actual_currency: str,
    ) -> None:
        super().__init__(
            "Payment amount or currency does not match booking evidence",
            details={
                "expectedAmount": expected_amount,
                "actualAmount": actual_amount,
                "expectedCurrency": expected_currency,
                "actualCurrency": actual_currency,
            },
        )


class BookingEvidenceRequired(PaymentError):
    code = "BOOKING_EVIDENCE_REQUIRED"
    http_status = 422

    def __init__(self) -> None:
        super().__init__("Authoritative booking payment evidence is required")


class ProviderReferenceConflict(PaymentError):
    code = "PROVIDER_REFERENCE_CONFLICT"
    http_status = 409

    def __init__(self) -> None:
        super().__init__("Provider reference does not match the payment")


class ProviderEventConflict(PaymentError):
    code = "PROVIDER_EVENT_CONFLICT"
    http_status = 409

    def __init__(self, event_id: str) -> None:
        super().__init__(
            "Provider event ID was already used for another payload",
            details={"eventId": event_id},
        )


class PaymentDeclined(PaymentError):
    code = "PAYMENT_DECLINED"
    http_status = 402

    def __init__(self, payment_id: str, reason: str) -> None:
        super().__init__(
            "Payment was declined by the provider",
            details={"paymentId": payment_id, "reason": reason},
        )


class PaymentUnknown(PaymentError):
    code = "PAYMENT_UNKNOWN"
    http_status = 409
    retryable = True

    def __init__(self, payment_id: str) -> None:
        super().__init__(
            "Payment outcome is unknown and requires reconciliation",
            details={"paymentId": payment_id},
        )


class ProviderUnavailable(PaymentError):
    code = "PROVIDER_UNAVAILABLE"
    http_status = 503
    retryable = True

    def __init__(self) -> None:
        super().__init__("Payment provider is temporarily unavailable")


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
