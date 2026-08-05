"""Cau hinh service, doc tu bien moi truong.

Quy uoc dat ten bien moi truong: tien to EVENT_ (giong CUSTOMER_ cua
customer-service, SEAT_ cua seat-inventory-service, IDENTITY_ cua
identity-service) de tranh dung do khi nhieu service chay chung mot may.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from libs.platform_security import ServiceJwtValidationSettings


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
    """Chuan hoa driver ve psycopg3 (giong quy uoc cua seat-inventory-service)."""
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+psycopg://", 1)
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+psycopg://", 1)
    return raw


@dataclass(frozen=True, slots=True)
class Settings:
    app_env: str
    log_level: str
    service_name: str
    database_url: str
    db_pool_size: int
    db_max_overflow: int
    sql_echo: bool
    service_jwt: ServiceJwtValidationSettings

    @classmethod
    def from_environment(cls) -> Settings:
        database_url = os.getenv("EVENT_DATABASE_URL", "").strip()
        if not database_url:
            raise ValueError("EVENT_DATABASE_URL is required")
        return cls(
            app_env=os.getenv("EVENT_APP_ENV", "local"),
            log_level=os.getenv("EVENT_LOG_LEVEL", "INFO").upper(),
            service_name="event-service",
            database_url=_normalize_database_url(database_url),
            db_pool_size=_integer("EVENT_DB_POOL_SIZE", 10, minimum=1, maximum=100),
            db_max_overflow=_integer(
                "EVENT_DB_MAX_OVERFLOW", 10, minimum=0, maximum=100
            ),
            sql_echo=os.getenv("EVENT_SQL_ECHO", "false").strip().lower()
            in {"1", "true", "yes", "on"},
            service_jwt=ServiceJwtValidationSettings.from_environment(
                "EVENT", audience="event-service"
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_environment()


def reset_settings_cache() -> None:
    """Cho phep test thay doi bien moi truong roi doc lai cau hinh."""
    get_settings.cache_clear()
