from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings


@dataclass(frozen=True, slots=True)
class ServiceEndpoint:
    logical_name: str
    base_url: str
    audience: str
    protocol: str = "REST"
    critical: bool = True
    health_base_url: str | None = None

    @property
    def readiness_url(self) -> str:
        base = (self.health_base_url or self.base_url).rstrip("/")
        return f"{base}/health/ready"


class ServiceRegistry:
    """Static logical-name registry with environment-configurable addresses."""

    def __init__(self, settings: Settings) -> None:
        seat_health_base = settings.seat_url.rstrip("/")
        if seat_health_base.endswith("/soap"):
            seat_health_base = seat_health_base[: -len("/soap")]

        self._items = {
            "identity": ServiceEndpoint(
                "identity",
                settings.identity_url,
                "identity-service",
            ),
            "customer": ServiceEndpoint(
                "customer",
                settings.customer_url,
                "customer-service",
            ),
            "event": ServiceEndpoint(
                "event",
                settings.event_url,
                "event-service",
            ),
            "seat": ServiceEndpoint(
                "seat",
                settings.seat_url,
                "seat-inventory-service",
                protocol="SOAP",
                health_base_url=seat_health_base,
            ),
            "booking": ServiceEndpoint(
                "booking",
                settings.booking_url,
                "booking-service",
            ),
            "payment": ServiceEndpoint(
                "payment",
                settings.payment_url,
                "payment-service",
            ),
            "ticket": ServiceEndpoint(
                "ticket",
                settings.ticket_url,
                "ticket-service",
            ),
            "notification": ServiceEndpoint(
                "notification",
                settings.notification_url,
                "notification-service",
                critical=False,
            ),
            "realtime": ServiceEndpoint(
                "realtime",
                settings.realtime_url,
                "realtime-status-service",
                critical=False,
            ),
        }

    def resolve(self, name: str) -> ServiceEndpoint:
        try:
            return self._items[name]
        except KeyError as exc:
            raise KeyError(f"Unknown logical service: {name}") from exc

    def snapshot(self) -> dict[str, ServiceEndpoint]:
        return dict(self._items)
