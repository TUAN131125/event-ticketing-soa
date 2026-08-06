from __future__ import annotations

import json
from pathlib import Path

import yaml

from app.main import create_app


def normalized(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def main() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    canonical_path = repository_root / "contracts" / "esb-public-api.yaml"
    snapshot_path = repository_root / "contracts" / "generated" / "esb-runtime.openapi.yaml"
    mirror_path = Path(__file__).resolve().parents[1] / "contracts" / "esb-public-api.yaml"

    runtime = create_app().state.generated_openapi()
    canonical = yaml.safe_load(canonical_path.read_text(encoding="utf-8"))
    snapshot = yaml.safe_load(snapshot_path.read_text(encoding="utf-8"))
    mirror = yaml.safe_load(mirror_path.read_text(encoding="utf-8"))

    expected = normalized(runtime)
    mismatches = [
        str(path)
        for path, document in (
            (canonical_path, canonical),
            (snapshot_path, snapshot),
            (mirror_path, mirror),
        )
        if normalized(document) != expected
    ]
    if mismatches:
        raise SystemExit("OpenAPI parity failed: " + ", ".join(mismatches))

    operations = sum(
        1
        for path_item in runtime.get("paths", {}).values()
        for method in path_item
        if method in {"get", "post", "put", "patch", "delete"}
    )
    print(
        f"OpenAPI parity PASS: {len(runtime.get('paths', {}))} paths, "
        f"{operations} operations, runtime == canonical == snapshot == mirror"
    )


if __name__ == "__main__":
    main()
