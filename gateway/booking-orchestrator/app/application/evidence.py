from __future__ import annotations

from typing import Any


def booking_evidence(
    *,
    provider_reference: str | None = None,
    reservation_expires_at: str | None = None,
    verified_at: str | None = None,
    reservation_released: bool = False,
    payment_refunded: bool = False,
    compensation_completed: bool | None = None,
    seat_confirmed: bool | None = None,
    tickets_issued: bool | None = None,
    payment_captured: bool | None = None,
    resolved_payment_status: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the closed Booking Service EvidenceRequest contract safely.

    Provider-specific or orchestration-specific data belongs under ``details``;
    putting arbitrary fields at the evidence root would violate the Booking v2
    contract because it has ``additionalProperties: false``.
    """

    result: dict[str, Any] = {
        "reservationReleased": reservation_released,
        "paymentRefunded": payment_refunded,
        "details": details or {},
    }
    optional = {
        "providerReference": provider_reference,
        "reservationExpiresAt": reservation_expires_at,
        "verifiedAt": verified_at,
        "compensationCompleted": compensation_completed,
        "seatConfirmed": seat_confirmed,
        "ticketsIssued": tickets_issued,
        "paymentCaptured": payment_captured,
        "resolvedPaymentStatus": resolved_payment_status,
    }
    result.update({key: value for key, value in optional.items() if value is not None})
    return result
