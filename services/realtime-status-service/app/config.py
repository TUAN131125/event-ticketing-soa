"""Environment-backed configuration with deny-by-default production validation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit


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
    app_name: str = "realtime-status-service"
    app_env: Literal["local", "test", "development", "staging", "production"] = "local"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    docs_enabled: bool = True
    allowed_ws_origins: tuple[str, ...] = ("http://localhost:3000", "http://localhost:3001")
    jwt_issuer: str = "http://localhost:8009"
    jwt_audience: str = "event-ticketing-api"
    jwks_url: str = "http://localhost:8009/.well-known/jwks.json"
    jwt_algorithm: str = "RS256"
    jwks_timeout_seconds: float = 2.0
    jwks_cache_ttl_seconds: int = 300
    internal_service_token: str = ""
    allowed_internal_callers: tuple[str, ...] = (
        "booking-orchestrator",
        "booking-service",
        "payment-service",
        "ticket-service",
    )
    booking_authorization_url: str = "http://localhost:8007/bookings/{bookingId}"
    booking_service_token: str = ""
    booking_client_timeout_seconds: float = 2.0
    admin_roles: tuple[str, ...] = ("ADMIN",)
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
    allow_query_token: bool = False
    insecure_auth_bypass: bool = False
    authoritative_booking_url_template: str = "/api/bookings/{bookingId}"

    def __post_init__(self) -> None:
        if self.idle_timeout_seconds <= self.heartbeat_interval_seconds:
            raise ValueError("idle timeout must be greater than heartbeat interval")
        if self.redis_required and not self.redis_url:
            raise ValueError("REALTIME_REDIS_REQUIRED requires REALTIME_REDIS_URL")
        if "{bookingId}" not in self.booking_authorization_url:
            raise ValueError("REALTIME_BOOKING_AUTHORIZATION_URL must contain {bookingId}")
        if "{bookingId}" not in self.authoritative_booking_url_template:
            raise ValueError("REALTIME_AUTHORITATIVE_BOOKING_URL_TEMPLATE must contain {bookingId}")
        if self.jwt_algorithm != "RS256":
            raise ValueError("Only RS256 is supported by the repository Identity contract")
        if self.app_env == "production":
            if "*" in self.allowed_ws_origins:
                raise ValueError("Wildcard WebSocket Origin is forbidden in production")
            if any(not origin.startswith("https://") for origin in self.allowed_ws_origins):
                raise ValueError("Production WebSocket origins must use HTTPS")
            if not self.jwt_issuer or not self.jwt_audience or not self.jwks_url:
                raise ValueError("JWT issuer, audience and JWKS URL are required")
            if not self.jwt_issuer.startswith("https://") or not self.jwks_url.startswith(
                "https://"
            ):
                raise ValueError("Production JWT issuer and JWKS URL must use HTTPS")
            if len(self.internal_service_token) < 32 or len(self.booking_service_token) < 32:
                raise ValueError("Production service tokens must be at least 32 characters")
            if self.internal_service_token == self.booking_service_token:
                raise ValueError(
                    "Inbound and Booking service credentials must be distinct in production"
                )
            if self.allow_query_token or self.insecure_auth_bypass:
                raise ValueError("Development authentication modes are forbidden in production")
        for url_name, url in (
            ("JWKS", self.jwks_url),
            ("Booking authorization", self.booking_authorization_url),
        ):
            parsed = urlsplit(url.replace("{bookingId}", "sample"))
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError(f"{url_name} URL must be HTTP(S)")

    @classmethod
    def from_environment(cls) -> Settings:
        env = os.getenv("REALTIME_APP_ENV", "local").strip().lower()
        if env not in {"local", "test", "development", "staging", "production"}:
            raise ValueError("REALTIME_APP_ENV is invalid")
        redis = os.getenv("REALTIME_REDIS_URL") or None
        return cls(
            app_env=env,  # type: ignore[arg-type]
            host=os.getenv("REALTIME_HOST", "127.0.0.1"),
            port=_int("REALTIME_PORT", 8000, 1, 65535),
            log_level=os.getenv("REALTIME_LOG_LEVEL", "INFO").upper(),
            docs_enabled=_bool("REALTIME_DOCS_ENABLED", env != "production"),
            allowed_ws_origins=_csv(
                "REALTIME_ALLOWED_WS_ORIGINS", "http://localhost:3000,http://localhost:3001"
            ),
            jwt_issuer=os.getenv("REALTIME_JWT_ISSUER", "http://localhost:8009").rstrip("/"),
            jwt_audience=os.getenv("REALTIME_JWT_AUDIENCE", "event-ticketing-api"),
            jwks_url=os.getenv("REALTIME_JWKS_URL", "http://localhost:8009/.well-known/jwks.json"),
            jwt_algorithm=os.getenv("REALTIME_JWT_ALGORITHM", "RS256"),
            jwks_timeout_seconds=_float("REALTIME_JWKS_TIMEOUT_SECONDS", 2, 0.1, 30),
            jwks_cache_ttl_seconds=_int("REALTIME_JWKS_CACHE_TTL_SECONDS", 300, 10, 86400),
            internal_service_token=os.getenv("REALTIME_INTERNAL_SERVICE_TOKEN", ""),
            allowed_internal_callers=_csv(
                "REALTIME_ALLOWED_INTERNAL_CALLERS",
                "booking-orchestrator,booking-service,payment-service,ticket-service",
            ),
            booking_authorization_url=os.getenv(
                "REALTIME_BOOKING_AUTHORIZATION_URL", "http://localhost:8007/bookings/{bookingId}"
            ),
            booking_service_token=os.getenv("REALTIME_BOOKING_SERVICE_TOKEN", ""),
            booking_client_timeout_seconds=_float(
                "REALTIME_BOOKING_CLIENT_TIMEOUT_SECONDS", 2, 0.1, 30
            ),
            admin_roles=_csv("REALTIME_ADMIN_ROLES", "ADMIN"),
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
            allow_query_token=_bool("REALTIME_ALLOW_QUERY_TOKEN", False),
            insecure_auth_bypass=_bool("REALTIME_INSECURE_AUTH_BYPASS", False),
            authoritative_booking_url_template=os.getenv(
                "REALTIME_AUTHORITATIVE_BOOKING_URL_TEMPLATE", "/api/bookings/{bookingId}"
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_environment()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
