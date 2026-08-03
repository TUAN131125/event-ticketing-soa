from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseModel):
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite+aiosqlite:///./booking-orchestrator.db"
    docs_enabled: bool = True
    log_level: str = "INFO"
    request_timeout_seconds: float = 15.0
    identity_jwks_url: str = "http://localhost:8009/.well-known/jwks.json"
    identity_expected_issuer: str = "identity-service"
    identity_expected_audience: str = "public-esb"
    identity_jwks_cache_seconds: int = 300
    customer_service_url: str = "http://localhost:8001"
    event_service_url: str = "http://localhost:8002"
    seat_service_url: str = "http://localhost:8003/soap"
    seat_service_token: str | None = None
    booking_service_url: str = "http://localhost:8004"
    payment_service_url: str = "http://localhost:8005"
    ticket_service_url: str = "http://localhost:8006"
    notification_service_url: str = "http://localhost:8007"
    notification_webhook_secret: str | None = None
    realtime_service_url: str = "http://localhost:8008"
    realtime_internal_service_token: str | None = None
    realtime_caller_service: str = "booking-orchestrator"
    internal_service_issuer: str = "booking-orchestrator"
    internal_service_subject: str = "booking-orchestrator"
    internal_service_audience: str = "provider-services"
    internal_service_private_key: str | None = None
    internal_service_key_id: str = "esb-internal-1"
    ws_ticket_issuer: str = "booking-orchestrator"
    ws_ticket_audience: str = "realtime-status-service"
    ws_ticket_private_key: str | None = None
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
    create_schema_on_start: bool = True
    verify_contract_freeze: bool = True
    seat_provider_xsd_path: Path = REPOSITORY_ROOT / "services" / "seat-inventory-service" / "contracts" / "seat-inventory.xsd"

    @model_validator(mode="after")
    def production_security(self) -> Settings:
        if self.environment == "production":
            if not self.database_url.startswith("postgresql+"):
                raise ValueError("production requires PostgreSQL")
            if not self.internal_service_private_key or not self.ws_ticket_private_key:
                raise ValueError("production signing keys must be supplied by secret reference")
            if not self.notification_webhook_secret or len(self.notification_webhook_secret) < 32:
                raise ValueError("production notification webhook secret must be at least 32 characters")
            if not self.seat_service_token or len(self.seat_service_token) < 32:
                raise ValueError("production Seat service token must be at least 32 characters")
            if not self.realtime_internal_service_token or len(self.realtime_internal_service_token) < 32:
                raise ValueError("production Realtime internal service token must be at least 32 characters")
            if self.docs_enabled:
                raise ValueError("production docs must be disabled")
            if self.create_schema_on_start:
                raise ValueError("production schema changes must run through Alembic")
        return self

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
