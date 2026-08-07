"""CI gate: the ESB implementation and its published contract must not drift.

The canonical document is curated (servers, a reusable parameter/response vocabulary,
UTC constraints, prose), so this compares meaning rather than bytes — see
`scripts/openapi_parity` for exactly which properties are held identical. The runtime
snapshot under `contracts/generated/` is a plain export and is still compared literally.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from app.main import create_app
from scripts.openapi_parity import compare


def main() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    canonical_path = repository_root / "contracts" / "esb-public-api.yaml"
    snapshot_path = repository_root / "contracts" / "generated" / "esb-runtime.openapi.yaml"
    mirror_path = Path(__file__).resolve().parents[1] / "contracts" / "esb-public-api.yaml"

    runtime = create_app().state.generated_openapi()
    canonical = yaml.safe_load(canonical_path.read_text(encoding="utf-8"))
    snapshot = yaml.safe_load(snapshot_path.read_text(encoding="utf-8"))
    mirror = yaml.safe_load(mirror_path.read_text(encoding="utf-8"))

    failures: list[str] = []

    drift = compare(runtime, canonical)
    if drift:
        failures.append(f"{canonical_path} has drifted from the runtime:\n  " + "\n  ".join(drift))

    # The snapshot is a verbatim export, so run `scripts/export_openapi.py` to refresh it.
    if snapshot != runtime:
        failures.append(f"{snapshot_path} is not the current runtime export")

    # The gateway-local mirror must stay a copy of the canonical document.
    if mirror != canonical:
        failures.append(f"{mirror_path} is not a copy of {canonical_path}")

    if failures:
        raise SystemExit("OpenAPI parity failed:\n" + "\n".join(failures))

    operations = sum(
        1
        for path_item in runtime.get("paths", {}).values()
        for method in path_item
        if method in {"get", "post", "put", "patch", "delete"}
    )
    print(
        f"OpenAPI parity PASS: {len(runtime.get('paths', {}))} paths, {operations} operations; "
        "runtime == canonical (semantic), snapshot == runtime, mirror == canonical"
    )


if __name__ == "__main__":
    main()
