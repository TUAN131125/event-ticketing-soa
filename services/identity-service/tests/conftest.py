"""Unit and PostgreSQL-backed test fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import Settings
from app.infrastructure.database.session import get_engine, get_session_factory
from app.main import create_app


def _test_settings(tmp_path: Path) -> Settings:
    repository_root = Path(__file__).resolve().parents[3]
    os.environ.setdefault(
        "IDENTITY_DATABASE_URL",
        "postgresql+psycopg://identity:identity@localhost:5432/identity_test",
    )
    os.environ.setdefault("IDENTITY_ISSUER", "http://localhost:8009")
    os.environ.setdefault(
        "IDENTITY_ALLOWED_ORIGINS",
        "http://testserver,http://localhost:3000",
    )
    os.environ.setdefault(
        "IDENTITY_PRIVATE_KEY_PATH",
        str(tmp_path / "bootstrap-private.pem"),
    )
    os.environ.setdefault(
        "IDENTITY_PUBLIC_KEY_PATH",
        str(tmp_path / "bootstrap-public.pem"),
    )
    os.environ.setdefault(
        "IDENTITY_OPENAPI_PATH",
        str(repository_root / "contracts" / "identity-service.yaml"),
    )
    base_settings = Settings.from_environment()
    database_url = os.getenv(
        "IDENTITY_TEST_DATABASE_URL",
        "postgresql+psycopg://identity:identity@localhost:5432/identity_test",
    )
    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    if not private_key.exists():
        from scripts.generate_keys import generate

        generate(private_key, public_key)
    return replace(
        base_settings,
        app_env="test",
        database_url=database_url,
        issuer="http://localhost:8009",
        audience="public-esb",
        cookie_secure=False,
        allowed_origins=("http://testserver", "http://localhost:3000"),
        private_key_path=private_key,
        public_key_path=public_key,
        argon2_time_cost=1,
        argon2_memory_cost_kib=8192,
        argon2_parallelism=1,
        login_rate_limit=20,
    )


@pytest.fixture(scope="session")
def unit_settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    return _test_settings(tmp_path_factory.mktemp("identity-unit-keys"))


@pytest.fixture(scope="session")
def postgres_settings(unit_settings: Settings) -> Settings:
    try:
        with get_engine(unit_settings).connect() as connection:
            connection.execute(text("SELECT 1"))
            if connection.scalar(text("SELECT to_regclass('identity.users')")) is None:
                pytest.skip("PostgreSQL identity schema is not migrated")
    except Exception as exc:
        pytest.skip(f"PostgreSQL integration database unavailable: {exc}")
    return unit_settings


@pytest.fixture
def clean_database(postgres_settings: Settings) -> Iterator[None]:
    factory = get_session_factory(postgres_settings)
    with factory() as session, session.begin():
        session.execute(
            text(
                "TRUNCATE identity.auth_rate_limits, identity.auth_audit, "
                "identity.refresh_sessions, identity.user_roles, identity.users "
                "RESTART IDENTITY CASCADE"
            )
        )
    yield


@pytest.fixture
def client(
    postgres_settings: Settings, clean_database: None
) -> Iterator[TestClient]:
    application = create_app(postgres_settings)
    with TestClient(application) as value:
        yield value


@pytest.fixture
def contract_client(unit_settings: Settings) -> TestClient:
    # OpenAPI is served without entering application lifespan, so contract tests
    # do not require the PostgreSQL driver or a running database.
    return TestClient(create_app(unit_settings))


@pytest.fixture
def context() -> object:
    from app.domain.value_objects import RequestContext

    return RequestContext(
        correlation_id="test-correlation",
        trace_id="1" * 32,
        client_ip="127.0.0.1",
        user_agent="pytest",
    )
