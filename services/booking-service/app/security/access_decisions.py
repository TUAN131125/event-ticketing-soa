"""Authoritative booking access decision using Customer identity mappings."""

import httpx
from libs.platform_security import ServiceJwtSigner

from app.application.service import BookingService


class BookingAccessAuthorizer:
    def __init__(
        self,
        booking_service: BookingService,
        customer_service_url: str,
        signer: ServiceJwtSigner,
        client: httpx.Client,
    ) -> None:
        if not customer_service_url:
            raise ValueError("BOOKING_CUSTOMER_SERVICE_URL is required")
        self._bookings = booking_service
        self._customer_url = customer_service_url
        self._signer = signer
        self._client = client

    def decide(
        self,
        *,
        booking_id: str,
        identity_subject: str,
        roles: frozenset[str],
        correlation_id: str,
    ) -> dict[str, object]:
        if "ADMIN" in roles:
            return self._result(True, "ADMIN_OVERRIDE", 5)
        try:
            booking = self._bookings.get(booking_id)
        except Exception as exc:  # noqa: BLE001 -- domain error is normalized below
            if getattr(exc, "code", "") == "BOOKING_NOT_FOUND":
                return self._result(False, "BOOKING_NOT_FOUND", 1)
            raise
        try:
            response = self._client.get(
                f"{self._customer_url}/internal/identity-mappings/{identity_subject}",
                headers={
                    "Authorization": (
                        f"Bearer {self._signer.issue('customer-service')}"
                    ),
                    "X-Correlation-ID": correlation_id,
                },
            )
        except httpx.HTTPError:
            return self._result(False, "DEPENDENCY_UNAVAILABLE", 0)
        if response.status_code == 404:
            return self._result(False, "IDENTITY_NOT_MAPPED", 1)
        if response.status_code >= 500:
            return self._result(False, "DEPENDENCY_UNAVAILABLE", 0)
        if response.status_code != 200:
            return self._result(False, "IDENTITY_NOT_MAPPED", 1)
        mapping = response.json()
        if mapping.get("status") != "ACTIVE":
            return self._result(False, "CUSTOMER_INACTIVE", 1)
        if mapping.get("customerId") != booking.customer_id:
            return self._result(False, "NOT_OWNER", 1)
        return self._result(True, "OWNER", 5)

    @staticmethod
    def _result(allowed: bool, reason: str, ttl: int) -> dict[str, object]:
        return {"allowed": allowed, "reasonCode": reason, "cacheTtlSeconds": ttl}
