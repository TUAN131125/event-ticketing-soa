"""Environment-backed configuration with secure production validation."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal


def _integer(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _boolean(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _origins(raw: str) -> tuple[str, ...]:
    values = tuple(
        value.strip().rstrip("/") for value in raw.split(",") if value.strip()
    )
    if "*" in values:
        raise ValueError("IDENTITY_ALLOWED_ORIGINS cannot contain '*' with credentials")
    return values


def _database_url() -> str:
    value = os.getenv(
        "IDENTITY_DATABASE_URL",
        "postgresql+psycopg://identity:identity@localhost:5434/identity",
    )
    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+psycopg://", 1)
    if value.startswith("postgresql://"):
        return value.replace("postgresql://", "postgresql+psycopg://", 1)
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    app_name: str
    app_env: str
    database_url: str
    issuer: str
    audience: str
    private_key_path: Path
    public_key_path: Path
    key_id: str
    access_token_ttl_seconds: int
    refresh_token_ttl_seconds: int
    cookie_secure: bool
    cookie_samesite: Literal["lax", "strict", "none"]
    allowed_origins: tuple[str, ...]
    login_window_seconds: int
    login_rate_limit: int
    lockout_threshold: int
    lockout_seconds: int
    argon2_time_cost: int
    argon2_memory_cost_kib: int
    argon2_parallelism: int
    db_pool_size: int
    db_max_overflow: int
    log_level: str
    docs_enabled: bool

    @classmethod
    def from_environment(cls) -> Settings:
        app_env = os.getenv("IDENTITY_APP_ENV", "local").lower()
        cookie_secure = _boolean(
            "IDENTITY_COOKIE_SECURE", default=app_env not in {"local", "test"}
        )
        same_site = os.getenv("IDENTITY_COOKIE_SAMESITE", "lax").lower()
        if same_site not in {"lax", "strict", "none"}:
            raise ValueError("IDENTITY_COOKIE_SAMESITE must be lax, strict or none")
        if same_site == "none" and not cookie_secure:
            raise ValueError("SameSite=None requires Secure cookies")
        issuer = os.getenv("IDENTITY_ISSUER", "http://localhost:8009").rstrip("/")
        allowed_origins = _origins(
            os.getenv(
                "IDENTITY_ALLOWED_ORIGINS",
                "http://localhost:3000,http://localhost:3001",
            )
        )
        if app_env == "production" and not cookie_secure:
            raise ValueError("Secure refresh cookies are required in production")
        if app_env == "production" and not issuer.startswith("https://"):
            raise ValueError("HTTPS issuer is required in production")
        return cls(
            app_name="identity-service",
            app_env=app_env,
            database_url=_database_url(),
            issuer=issuer,
            audience=os.getenv("IDENTITY_AUDIENCE", "event-ticketing-api"),
            private_key_path=Path(
                os.getenv("IDENTITY_PRIVATE_KEY_PATH", "./keys/private.pem")
            ),
            public_key_path=Path(
                os.getenv("IDENTITY_PUBLIC_KEY_PATH", "./keys/public.pem")
            ),
            key_id=os.getenv("IDENTITY_KEY_ID", "identity-local-1"),
            access_token_ttl_seconds=_integer(
                "IDENTITY_ACCESS_TOKEN_TTL_SECONDS", 900, 60, 3600
            ),
            refresh_token_ttl_seconds=_integer(
                "IDENTITY_REFRESH_TOKEN_TTL_SECONDS", 604_800, 300, 2_592_000
            ),
            cookie_secure=cookie_secure,
            cookie_samesite=same_site,  # type: ignore[arg-type]
            allowed_origins=allowed_origins,
            login_window_seconds=_integer(
                "IDENTITY_LOGIN_WINDOW_SECONDS", 60, 10, 3600
            ),
            login_rate_limit=_integer("IDENTITY_LOGIN_RATE_LIMIT", 10, 1, 1000),
            lockout_threshold=_integer("IDENTITY_LOCKOUT_THRESHOLD", 5, 2, 100),
            lockout_seconds=_integer("IDENTITY_LOCKOUT_SECONDS", 300, 10, 86_400),
            argon2_time_cost=_integer("IDENTITY_ARGON2_TIME_COST", 3, 1, 10),
            argon2_memory_cost_kib=_integer(
                "IDENTITY_ARGON2_MEMORY_COST_KIB", 65_536, 8_192, 1_048_576
            ),
            argon2_parallelism=_integer("IDENTITY_ARGON2_PARALLELISM", 4, 1, 16),
            db_pool_size=_integer("IDENTITY_DB_POOL_SIZE", 10, 1, 100),
            db_max_overflow=_integer("IDENTITY_DB_MAX_OVERFLOW", 20, 0, 100),
            log_level=os.getenv("IDENTITY_LOG_LEVEL", "INFO").upper(),
            docs_enabled=_boolean(
                "IDENTITY_DOCS_ENABLED", default=app_env != "production"
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_environment()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
