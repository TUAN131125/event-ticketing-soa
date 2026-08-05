from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings


@pytest.fixture(autouse=True)
def required_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[4]
    monkeypatch.setenv(
        "IDENTITY_DATABASE_URL",
        "postgresql+psycopg://identity:test@localhost:5432/identity",
    )
    monkeypatch.setenv("IDENTITY_ISSUER", "http://localhost:8009")
    monkeypatch.setenv("IDENTITY_ALLOWED_ORIGINS", "http://localhost:3000")
    monkeypatch.setenv("IDENTITY_PRIVATE_KEY_PATH", str(tmp_path / "private.pem"))
    monkeypatch.setenv("IDENTITY_PUBLIC_KEY_PATH", str(tmp_path / "public.pem"))
    monkeypatch.setenv(
        "IDENTITY_OPENAPI_PATH",
        str(repository_root / "contracts" / "identity-service.yaml"),
    )


def test_configuration_rejects_empty_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("IDENTITY_AUDIENCE", "   ")
    with pytest.raises(ValueError, match="IDENTITY_AUDIENCE cannot be empty"):
        Settings.from_environment()


def test_configuration_rejects_unknown_log_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IDENTITY_LOG_LEVEL", "verbose")
    with pytest.raises(ValueError, match="IDENTITY_LOG_LEVEL must be one of"):
        Settings.from_environment()


def test_database_url_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("IDENTITY_DATABASE_URL")
    with pytest.raises(ValueError, match="IDENTITY_DATABASE_URL is required"):
        Settings.from_environment()


def test_environment_file_is_not_loaded_implicitly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "IDENTITY_DATABASE_URL="
        "postgresql+psycopg://identity:file-password@localhost:5432/identity\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("IDENTITY_ENV_FILE", str(env_file))
    monkeypatch.delenv("IDENTITY_DATABASE_URL")

    with pytest.raises(ValueError, match="IDENTITY_DATABASE_URL is required"):
        Settings.from_environment()
