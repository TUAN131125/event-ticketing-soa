"""Cau hinh service, doc tu bien moi truong.

Quy uoc dat ten bien moi truong: tien to NOTIFICATION_ (giong CUSTOMER_ cua
customer-service, SEAT_ cua seat-inventory-service) de tranh dung do khi
nhieu service chay chung mot may.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _integer(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} phai la so nguyen") from exc
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} phai nam trong khoang [{minimum}, {maximum}]")
    return value


def _normalize_database_url(raw: str) -> str:
    """Chuan hoa driver ve psycopg3 (giong quy uoc cua customer-service)."""
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+psycopg://", 1)
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw


def _read_public_key(path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str
    log_level: str
    service_name: str
    database_url: str
    db_pool_size: int
    db_max_overflow: int
    sql_echo: bool
    webhook_shared_secret: str
    jwt_public_key: str | None
    jwt_issuer: str
    jwt_audience: str

    @classmethod
    def from_environment(cls) -> "Settings":
        database_url = os.getenv(
            "NOTIFICATION_DATABASE_URL",
            "postgresql+psycopg://notification_service:notification_service"
            "@localhost:5437/notification_service",
        )
        return cls(
            app_env=os.getenv("NOTIFICATION_APP_ENV", "local"),
            log_level=os.getenv("NOTIFICATION_LOG_LEVEL", "INFO").upper(),
            service_name="notification-service",
            database_url=_normalize_database_url(database_url),
            db_pool_size=_integer("NOTIFICATION_DB_POOL_SIZE", 10, minimum=1, maximum=100),
            db_max_overflow=_integer(
                "NOTIFICATION_DB_MAX_OVERFLOW", 10, minimum=0, maximum=100
            ),
            sql_echo=os.getenv("NOTIFICATION_SQL_ECHO", "false").strip().lower()
            in {"1", "true", "yes", "on"},
            # NOT-02: bi mat dung chung voi ben phat webhook (ESB) de xac
            # minh chu ky HMAC-SHA256 (xem security/webhook_signature.py).
            # Gia tri mac dinh CHI danh cho local/dev - bat buoc doi trong
            # moi moi truong that.
            webhook_shared_secret=os.getenv(
                "NOTIFICATION_WEBHOOK_SHARED_SECRET", "dev-only-shared-secret-change-me"
            ),
            # RS256 public key cua Identity Service - xem security/authentication.py.
            jwt_public_key=_read_public_key(os.getenv("NOTIFICATION_JWT_PUBLIC_KEY_PATH")),
            jwt_issuer=os.getenv("NOTIFICATION_JWT_ISSUER", "identity-service"),
            jwt_audience=os.getenv("NOTIFICATION_JWT_AUDIENCE", "event-ticketing-soa"),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_environment()


def reset_settings_cache() -> None:
    """Cho phep test thay doi bien moi truong roi doc lai cau hinh."""
    get_settings.cache_clear()
