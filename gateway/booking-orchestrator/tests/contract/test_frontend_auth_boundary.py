from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[4]
FRONTEND = ROOT / "frontend"


def test_frontend_auth_uses_only_esb_public_url_and_paths():
    paths = [
        FRONTEND / "customer-web/src/api/auth-client.ts",
        FRONTEND / "admin-web/src/api/auth.ts",
        FRONTEND / "customer-web/.env.example",
        FRONTEND / "admin-web/.env.example",
        FRONTEND / "customer-web/Dockerfile",
        FRONTEND / "admin-web/Dockerfile",
        FRONTEND / "customer-web/vite.config.ts",
        FRONTEND / "customer-web/README.md",
        FRONTEND / "admin-web/README.md",
        FRONTEND / "README.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    assert "VITE_IDENTITY_API_URL" not in combined
    assert "localhost:8009" not in combined
    assert "VITE_ESB_API_URL" in combined
    for route in (
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/refresh",
        "/api/auth/logout",
        "/api/auth/me",
    ):
        assert route in combined


def test_frontend_contract_generator_reads_provider_contracts_from_real_paths():
    scripts = [
        (FRONTEND / "scripts/generate-esb-types.mjs").read_text(encoding="utf-8"),
        (FRONTEND / "scripts/generate_esb_types.py").read_text(encoding="utf-8"),
    ]
    script = "\n".join(scripts)
    for path in (
        "providers/identity-service.yaml",
        "providers/realtime-status-service.yaml",
        "providers/realtime-status.asyncapi.yaml",
    ):
        assert path in script
        assert (ROOT / "contracts" / path).exists()


def test_frontend_does_not_expose_direct_realtime_url():
    paths = [
        FRONTEND / "customer-web/.env.example",
        FRONTEND / "admin-web/.env.example",
        FRONTEND / "customer-web/Dockerfile",
        FRONTEND / "admin-web/Dockerfile",
        FRONTEND / "customer-web/vite.config.ts",
        FRONTEND / "customer-web/README.md",
        FRONTEND / "admin-web/README.md",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths)
    socket = (FRONTEND / "customer-web/src/api/websocket-client.ts").read_text(encoding="utf-8")
    assert "VITE_REALTIME_WS_URL" not in combined
    assert "localhost:8008" not in combined
    assert "VITE_REALTIME_WS_URL" not in socket
    assert "return '';" in socket


def test_compose_builds_frontends_with_only_the_esb_public_url():
    compose_path = ROOT / "compose.yaml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    for service_name in ("customer-web", "admin-web"):
        args = compose["services"][service_name]["build"]["args"]
        assert set(args) == {"VITE_ESB_API_URL"}
    root_env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "VITE_IDENTITY_API_URL" not in root_env
    assert "VITE_REALTIME_WS_URL" not in root_env
    assert "ESB_IDENTITY_SERVICE_URL=http://identity:8009" in root_env
