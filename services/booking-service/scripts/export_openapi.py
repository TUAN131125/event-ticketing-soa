"""Export the runtime FastAPI schema as the versioned static contract."""

from __future__ import annotations

from pathlib import Path

import yaml

from app.config import Settings
from app.main import create_app


def export(destination: Path) -> None:
    settings = Settings(
        app_name="booking-service",
        app_env="contract",
        database_url="postgresql+psycopg://booking:booking@localhost:5432/booking",
        service_token="contract-export-token",
        db_pool_size=1,
        db_max_overflow=0,
        db_pool_timeout_seconds=1,
        db_connect_timeout_seconds=1,
        db_lock_timeout_ms=1_000,
        db_statement_timeout_ms=5_000,
        idempotency_ttl_seconds=86_400,
        log_level="WARNING",
        docs_enabled=True,
    )
    schema = create_app(settings).openapi()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        yaml.safe_dump(schema, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    export(root / "contracts" / "openapi" / "booking-service.yaml")
