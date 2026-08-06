from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SEAT_XSD = PROJECT_ROOT / "contracts" / "seat-inventory.xsd"


class Settings(BaseModel):
    environment: Literal["development", "test", "production"] = "development"
    app_name: str = "booking-orchestrator"
    database_url: str = "sqlite:////tmp/esb_workflows.db"
    docs_enabled: bool = True
    log_level: str = "INFO"
    allowed_origins: str = ""

    # Existing gateway environment names are preserved.
    identity_service_url: str = "http://identity-service:8009"
    customer_service_url: str = "http://customer-service:8001"
    event_service_url: str = "http://event-service:8002"
    seat_service_url: str = "http://seat-inventory-service:8003/soap"
    booking_service_url: str = "http://booking-service:8004"
    payment_service_url: str = "http://payment-service:8005"
    ticket_service_url: str = "http://ticket-service:8006"
    notification_service_url: str = "http://notification-service:8007"
    notification_webhook_secret: str = ""
    realtime_service_url: str = "http://realtime-status-service:8008"

    request_timeout_seconds: float = Field(default=15.0, gt=0, le=120)
    dependency_timeout_seconds: float = Field(default=4.0, gt=0, le=60)
    max_safe_read_attempts: int = Field(default=3, ge=1, le=5)
    max_idempotent_command_attempts: int = Field(default=2, ge=1, le=5)
    bulkhead_limit: int = Field(default=20, ge=1, le=500)

    reservation_ttl_seconds: int = Field(default=600, ge=30, le=3600)
    reconciliation_poll_seconds: float = Field(default=2.0, gt=0, le=300)
    reconciliation_batch_size: int = Field(default=50, ge=1, le=500)
    outbox_max_attempts: int = Field(default=8, ge=1, le=100)
    outbox_batch_size: int = Field(default=50, ge=1, le=500)

    realtime_ticket_rate_limit: int = Field(default=10, ge=1, le=10_000)
    checkin_rate_limit: int = Field(default=60, ge=1, le=10_000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)

    # Public browser token verification. The old setting names are the canonical
    # deployment interface; the shorter names remain supported through aliases.
    identity_jwks_url: str = ""
    identity_expected_issuer: str = "identity-service"
    identity_expected_audience: str = "public-esb"
    jwt_shared_secret: str = ""  # controlled local HS256 fallback only

    # Internal service identity. Production uses short-lived RS256 service JWTs.
    internal_service_issuer: str = "booking-orchestrator"
    internal_service_subject: str = "booking-orchestrator"
    internal_service_private_key: str | None = None
    internal_service_private_key_path: Path | None = None
    internal_service_key_id: str = "esb-internal-1"
    service_token: str = ""  # controlled local static-token fallback only

    # One-time Realtime WebSocket ticket. Production uses RS256; local tests may
    # use an HMAC secret to avoid carrying private key files.
    ws_ticket_issuer: str = "booking-orchestrator"
    ws_ticket_audience: str = "realtime-status-service"
    ws_ticket_private_key: str | None = None
    ws_ticket_private_key_path: Path | None = None
    ws_ticket_key_id: str = "esb-ws-1"
    ws_ticket_signing_secret: str = ""
    ws_ticket_ttl_seconds: int = Field(default=45, ge=1, le=60)

    enable_workers: bool = True
    seat_provider_xsd_path: Path | None = DEFAULT_SEAT_XSD

    @classmethod
    def from_env(cls) -> "Settings":
        values: dict[str, object] = {}
        for name, field in cls.model_fields.items():
            raw = os.getenv(f"ESB_{name.upper()}")
            if raw is None:
                continue
            values[name] = cls._coerce_env_value(raw, field.annotation)

        # Backward-compatible aliases used by earlier generated compose files and
        # by the first ESB refactor draft.
        aliases = {
            "identity_service_url": ("ESB_IDENTITY_URL",),
            "customer_service_url": ("ESB_CUSTOMER_URL",),
            "event_service_url": ("ESB_EVENT_URL",),
            "seat_service_url": ("ESB_SEAT_URL",),
            "booking_service_url": ("ESB_BOOKING_URL",),
            "payment_service_url": ("ESB_PAYMENT_URL",),
            "ticket_service_url": ("ESB_TICKET_URL",),
            "notification_service_url": ("ESB_NOTIFICATION_URL",),
            "realtime_service_url": ("ESB_REALTIME_URL",),
            "identity_jwks_url": ("ESB_JWKS_URL",),
            "identity_expected_issuer": ("ESB_JWT_ISSUER",),
            "identity_expected_audience": ("ESB_JWT_AUDIENCE",),
            "max_safe_read_attempts": ("ESB_SAFE_READ_ATTEMPTS",),
            "max_idempotent_command_attempts": (
                "ESB_IDEMPOTENT_COMMAND_ATTEMPTS",
            ),
        }
        for field_name, environment_names in aliases.items():
            if field_name in values:
                continue
            for environment_name in environment_names:
                raw = os.getenv(environment_name)
                if raw is not None:
                    field = cls.model_fields[field_name]
                    values[field_name] = cls._coerce_env_value(raw, field.annotation)
                    break

        if values.get("environment") == "local":
            values["environment"] = "development"
        return cls.model_validate(values)

    @staticmethod
    def _coerce_env_value(raw: str, annotation: object) -> object:
        if annotation is bool:
            return raw.lower() in {"1", "true", "yes", "on"}
        return raw.replace("\\n", "\n")

    @model_validator(mode="after")
    def validate_production(self) -> "Settings":
        if self.environment == "production":
            if not self.database_url.startswith("postgresql+"):
                raise ValueError("production requires a PostgreSQL database URL")
            if not self.identity_jwks_url:
                raise ValueError("production requires ESB_IDENTITY_JWKS_URL")
            if not (
                self.internal_service_private_key
                or self.internal_service_private_key_path
            ):
                raise ValueError(
                    "production requires ESB_INTERNAL_SERVICE_PRIVATE_KEY or its path"
                )
            if not self.ws_ticket_private_key and not self.ws_ticket_private_key_path:
                raise ValueError(
                    "production requires ESB_WS_TICKET_PRIVATE_KEY or its path"
                )
            if len(self.notification_webhook_secret) < 32:
                raise ValueError(
                    "production requires ESB_NOTIFICATION_WEBHOOK_SECRET with at least 32 characters"
                )
            origins = self.origin_list()
            if not origins or "*" in origins:
                raise ValueError("production CORS origins must be explicit")
            if self.docs_enabled:
                raise ValueError("production OpenAPI documentation must be disabled")
        return self

    def origin_list(self) -> list[str]:
        return [
            item.strip().rstrip("/")
            for item in self.allowed_origins.split(",")
            if item.strip()
        ]

    def validate(self) -> None:
        self.validate_production()

    # Properties preserve the compact names used inside the refactored source.
    @property
    def identity_url(self) -> str:
        return self.identity_service_url

    @property
    def customer_url(self) -> str:
        return self.customer_service_url

    @property
    def event_url(self) -> str:
        return self.event_service_url

    @property
    def seat_url(self) -> str:
        return self.seat_service_url

    @property
    def booking_url(self) -> str:
        return self.booking_service_url

    @property
    def payment_url(self) -> str:
        return self.payment_service_url

    @property
    def ticket_url(self) -> str:
        return self.ticket_service_url

    @property
    def notification_url(self) -> str:
        return self.notification_service_url

    @property
    def realtime_url(self) -> str:
        return self.realtime_service_url

    @property
    def jwks_url(self) -> str:
        return self.identity_jwks_url

    @property
    def jwt_issuer(self) -> str:
        return self.identity_expected_issuer

    @property
    def jwt_audience(self) -> str:
        return self.identity_expected_audience
