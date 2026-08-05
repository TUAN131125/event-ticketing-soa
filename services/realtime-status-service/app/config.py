"""Environment-backed configuration with deny-by-default production validation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from libs.platform_security import ServiceJwtValidationSettings


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _float(name: str, default: float, minimum: float, maximum: float) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _csv(name: str, default: str) -> tuple[str, ...]:
    values = tuple(
        value.strip().rstrip("/") for value in os.getenv(name, default).split(",") if value.strip()
    )
    if not values:
        raise ValueError(f"{name} must contain at least one value")
    return values


@dataclass(frozen=True, slots=True)
class Settings:
    host: str
    allowed_ws_origins: tuple[str, ...]
    service_jwt: ServiceJwtValidationSettings
    app_name: str = "realtime-status-service"
    app_env: Literal["local", "test", "development", "staging", "production"] = "local"
    port: int = 8008
    log_level: str = "INFO"
    docs_enabled: bool = True
    redis_url: str | None = None
    redis_required: bool = False
    redis_channel: str = "realtime.booking-status.v1"
    heartbeat_interval_seconds: float = 20.0
    idle_timeout_seconds: float = 60.0
    send_timeout_seconds: float = 2.0
    max_connections: int = 1000
    max_connections_per_principal: int = 5
    max_connections_per_ip: int = 20
    handshake_rate_limit: int = 30
    handshake_rate_window_seconds: int = 60
    max_event_bytes: int = 8192
    max_client_message_bytes: int = 1024
    dedup_ttl_seconds: int = 300
    dedup_max_entries: int = 10000
    sequence_cache_ttl_seconds: int = 1800
    sequence_max_entries: int = 10000
    cleanup_interval_seconds: float = 30.0
    graceful_shutdown_timeout_seconds: float = 10.0
    authoritative_booking_url_template: str = "/api/bookings/{bookingId}"
    ws_ticket_public_key_path: Path | None = None
    ws_ticket_issuer: str = "booking-orchestrator"
    ws_ticket_audience: str = "realtime-status-service"
    ws_ticket_key_id: str | None = None
    ws_ticket_max_ttl_seconds: int = 60
    ws_ticket_auth_timeout_seconds: float = 5.0
    ws_ticket_replay_max_entries: int = 10000

    def __post_init__(self) -> None:
        if self.idle_timeout_seconds <= self.heartbeat_interval_seconds:
            raise ValueError("idle timeout must be greater than heartbeat interval")
        if self.redis_required and not self.redis_url:
            raise ValueError("REALTIME_REDIS_REQUIRED requires REALTIME_REDIS_URL")
        if "{bookingId}" not in self.authoritative_booking_url_template:
            raise ValueError("REALTIME_AUTHORITATIVE_BOOKING_URL_TEMPLATE must contain {bookingId}")
        if not 1 <= self.ws_ticket_max_ttl_seconds <= 60:
            raise ValueError("REALTIME_WS_TICKET_MAX_TTL_SECONDS must be between 1 and 60")
        if self.app_env == "production":
            if "*" in self.allowed_ws_origins:
                raise ValueError("Wildcard WebSocket Origin is forbidden in production")
            if any(not origin.startswith("https://") for origin in self.allowed_ws_origins):
                raise ValueError("Production WebSocket origins must use HTTPS")
            if self.ws_ticket_public_key_path is None:
                raise ValueError("Production WebSocket ticket public key is required")
            try:
                key = serialization.load_pem_public_key(self.ws_ticket_public_key_path.read_bytes())
            except (OSError, ValueError, TypeError) as exc:
                raise ValueError("Production WebSocket ticket public key is invalid") from exc
            if not isinstance(key, RSAPublicKey):
                raise ValueError("Production WebSocket ticket public key must be RSA")

    @classmethod
    def from_environment(cls) -> Settings:
        env = os.getenv("REALTIME_APP_ENV", "local").strip().lower()
        if env not in {"local", "test", "development", "staging", "production"}:
            raise ValueError("REALTIME_APP_ENV is invalid")
        required = {
            name: os.getenv(name, "").strip()
            for name in (
                "REALTIME_HOST",
                "REALTIME_ALLOWED_WS_ORIGINS",
            )
        }
        missing = next((name for name, value in required.items() if not value), None)
        if missing is not None:
            raise ValueError(f"{missing} is required")
        redis = os.getenv("REALTIME_REDIS_URL") or None
        return cls(
            app_env=env,  # type: ignore[arg-type]
            host=required["REALTIME_HOST"],
            port=_int("REALTIME_PORT", 8008, 1, 65535),
            log_level=os.getenv("REALTIME_LOG_LEVEL", "INFO").upper(),
            docs_enabled=_bool("REALTIME_DOCS_ENABLED", env != "production"),
            allowed_ws_origins=_csv(
                "REALTIME_ALLOWED_WS_ORIGINS",
                required["REALTIME_ALLOWED_WS_ORIGINS"],
            ),
            service_jwt=ServiceJwtValidationSettings.from_environment(
                "REALTIME",
                audience="realtime-status-service",
                default_allowed_subjects=(
                    "booking-orchestrator,booking-service,payment-service,ticket-service"
                ),
            ),
            redis_url=redis,
            redis_required=_bool("REALTIME_REDIS_REQUIRED", False),
            redis_channel=os.getenv("REALTIME_REDIS_CHANNEL", "realtime.booking-status.v1"),
            heartbeat_interval_seconds=_float("REALTIME_HEARTBEAT_INTERVAL_SECONDS", 20, 0.1, 300),
            idle_timeout_seconds=_float("REALTIME_IDLE_TIMEOUT_SECONDS", 60, 0.2, 900),
            send_timeout_seconds=_float("REALTIME_SEND_TIMEOUT_SECONDS", 2, 0.05, 30),
            max_connections=_int("REALTIME_MAX_CONNECTIONS", 1000, 1, 100000),
            max_connections_per_principal=_int("REALTIME_MAX_CONNECTIONS_PER_PRINCIPAL", 5, 1, 100),
            max_connections_per_ip=_int("REALTIME_MAX_CONNECTIONS_PER_IP", 20, 1, 1000),
            handshake_rate_limit=_int("REALTIME_HANDSHAKE_RATE_LIMIT", 30, 1, 10000),
            handshake_rate_window_seconds=_int(
                "REALTIME_HANDSHAKE_RATE_WINDOW_SECONDS", 60, 1, 3600
            ),
            max_event_bytes=_int("REALTIME_MAX_EVENT_BYTES", 8192, 512, 1048576),
            max_client_message_bytes=_int("REALTIME_MAX_CLIENT_MESSAGE_BYTES", 1024, 64, 65536),
            dedup_ttl_seconds=_int("REALTIME_DEDUP_TTL_SECONDS", 300, 1, 86400),
            dedup_max_entries=_int("REALTIME_DEDUP_MAX_ENTRIES", 10000, 1, 1000000),
            sequence_cache_ttl_seconds=_int("REALTIME_SEQUENCE_CACHE_TTL_SECONDS", 1800, 1, 86400),
            sequence_max_entries=_int("REALTIME_SEQUENCE_MAX_ENTRIES", 10000, 1, 1000000),
            cleanup_interval_seconds=_float("REALTIME_CLEANUP_INTERVAL_SECONDS", 30, 0.1, 3600),
            graceful_shutdown_timeout_seconds=_float(
                "REALTIME_GRACEFUL_SHUTDOWN_TIMEOUT_SECONDS", 10, 0.1, 120
            ),
            authoritative_booking_url_template=os.getenv(
                "REALTIME_AUTHORITATIVE_BOOKING_URL_TEMPLATE", "/api/bookings/{bookingId}"
            ),
            ws_ticket_public_key_path=(
                Path(value) if (value := os.getenv("REALTIME_WS_TICKET_PUBLIC_KEY_PATH")) else None
            ),
            ws_ticket_issuer=os.getenv("REALTIME_WS_TICKET_ISSUER", "booking-orchestrator"),
            ws_ticket_audience=os.getenv("REALTIME_WS_TICKET_AUDIENCE", "realtime-status-service"),
            ws_ticket_key_id=os.getenv("REALTIME_WS_TICKET_KEY_ID") or None,
            ws_ticket_max_ttl_seconds=_int("REALTIME_WS_TICKET_MAX_TTL_SECONDS", 60, 1, 60),
            ws_ticket_auth_timeout_seconds=_float(
                "REALTIME_WS_TICKET_AUTH_TIMEOUT_SECONDS", 5, 0.05, 5
            ),
            ws_ticket_replay_max_entries=_int(
                "REALTIME_WS_TICKET_REPLAY_MAX_ENTRIES", 10000, 1, 1000000
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_environment()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
