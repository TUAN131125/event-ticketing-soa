"""Fail-closed booking authorization through a public HTTP service contract."""

from __future__ import annotations

import logging
from typing import Protocol
from urllib.parse import quote

import httpx

from app.config import Settings
from app.security.token_validation import AuthenticatedPrincipal

LOGGER = logging.getLogger("realtime.booking_access")


class BookingAccessChecker(Protocol):
    async def can_subscribe(
        self, principal: AuthenticatedPrincipal, booking_id: str, correlation_id: str
    ) -> bool: ...


class HttpBookingAccessChecker:
    """Consult Booking/ESB without accessing another service's database."""

    def __init__(self, settings: Settings, *, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._client = client

    async def can_subscribe(
        self, principal: AuthenticatedPrincipal, booking_id: str, correlation_id: str
    ) -> bool:
        if not set(self._settings.admin_roles).isdisjoint(principal.roles):
            return True
        url = self._settings.booking_authorization_url.replace(
            "{bookingId}", quote(booking_id, safe="")
        )
        headers = {
            "X-Service-Token": self._settings.booking_service_token,
            "X-Caller-Service": self._settings.app_name,
            "X-Actor-ID": principal.subject,
            "X-Correlation-ID": correlation_id,
            "Accept": "application/json",
        }
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self._settings.booking_client_timeout_seconds
        )
        try:
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                return False
            body = response.json()
            if not isinstance(body, dict):
                return False
            if body.get("allowed") is True:
                return True
            owner = body.get("customerId")
            trusted_identity = principal.customer_id or principal.subject
            return isinstance(owner, str) and owner == trusted_identity
        except (httpx.HTTPError, ValueError, TypeError):
            LOGGER.warning(
                "Booking authorization dependency failed",
                extra={
                    "operation": "booking_authorization",
                    "outcome": "fail_closed",
                    "correlationId": correlation_id,
                },
            )
            return False
        finally:
            if owns_client:
                await client.aclose()
