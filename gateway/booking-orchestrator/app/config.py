from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Settings(BaseModel):
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite+aiosqlite:///./booking-orchestrator.db"
    docs_enabled: bool = True
    log_level: str = "INFO"
    request_timeout_seconds: float = 15.0
    identity_jwks_url: str = ""
    identity_expected_issuer: str = "identity-service"
    identity_expected_audience: str = "public-esb"
    identity_jwks_cache_seconds: int = 300
    customer_service_url: str = ""
    event_service_url: str = ""
    seat_service_url: str = ""
    booking_service_url: str = ""
    payment_service_url: str = ""
    ticket_service_url: str = ""
    notification_service_url: str = ""
    notification_webhook_secret: str | None = None
    realtime_service_url: str = ""
    allowed_origins: str = ""
    internal_service_issuer: str = "booking-orchestrator"
    internal_service_subject: str = "booking-orchestrator"
    internal_service_private_key: str | None = None
    internal_service_private_key_path: Path | None = None
    internal_service_key_id: str = "esb-internal-1"
    ws_ticket_issuer: str = "booking-orchestrator"
    ws_ticket_audience: str = "realtime-status-service"
    ws_ticket_private_key: str | None = None
    ws_ticket_private_key_path: Path | None = None
    ws_ticket_key_id: str = "esb-ws-1"
    ws_ticket_ttl_seconds: int = Field(default=45, ge=1, le=60)
    safe_read_attempts: int = Field(default=2, ge=1, le=5)
    idempotent_command_attempts: int = Field(default=2, ge=1, le=5)
    retry_base_seconds: float = Field(default=0.01, ge=0, le=5)
    circuit_failure_threshold: int = Field(default=3, ge=1)
    circuit_recovery_seconds: float = Field(default=10.0, gt=0)
    bulkhead_limit: int = Field(default=20, ge=1)
    outbox_poll_seconds: float = Field(default=1.0, gt=0)
    reconciliation_poll_seconds: float = Field(default=1.0, gt=0)
    health_probe_timeout_seconds: float = Field(default=2.0, gt=0, le=10)
    booking_retry_after_seconds: int = Field(default=5, ge=1, le=300)
    reconciliation_deadline_seconds: int = Field(default=900, ge=60, le=86_400)
    reconciliation_backoff_seconds: int = Field(default=15, ge=1, le=3600)
    reconciliation_lease_seconds: int = Field(default=60, ge=5, le=3600)
    max_reservation_extensions: int = Field(default=3, ge=0, le=20)
    reservation_extension_seconds: int = Field(default=300, ge=30, le=3600)
    verify_contract_freeze: bool = True
    seat_provider_xsd_path: Path = Path("contracts/seat-inventory.xsd")

    @model_validator(mode="after")
    def production_security(self) -> Settings:
        if self.environment == "production":
            if not self.database_url.startswith("postgresql+"):
                raise ValueError("production requires PostgreSQL")
            if not (self.internal_service_private_key or self.internal_service_private_key_path) or not (
                self.ws_ticket_private_key or self.ws_ticket_private_key_path
            ):
                raise ValueError("production signing keys must be supplied by secret reference")
            if not self.notification_webhook_secret or len(self.notification_webhook_secret) < 32:
                raise ValueError("production notification webhook secret must be at least 32 characters")
            origins = self.origin_list()
            if not origins or "*" in origins:
                raise ValueError("production CORS origins must be explicit")
            if self.docs_enabled:
                raise ValueError("production docs must be disabled")
        return self

    def origin_list(self) -> list[str]:
        return [item.strip().rstrip("/") for item in self.allowed_origins.split(",") if item.strip()]

    @classmethod
    def from_env(cls) -> Settings:
        values: dict[str, object] = {}
        for name, field in cls.model_fields.items():
            env_name = f"ESB_{name.upper()}"
            raw = os.getenv(env_name)
            if raw is None:
                continue
            annotation = field.annotation
            if annotation is bool:
                values[name] = raw.lower() in {"1", "true", "yes", "on"}
            else:
                values[name] = raw.replace("\\n", "\n")
        return cls.model_validate(values)
