from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from app.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Export the OpenAPI generated from FastAPI decorators into the runtime "
            "snapshot used by CI. This never writes contracts/esb-public-api.yaml: that "
            "document is curated by hand and only has to stay semantically equivalent, "
            "which scripts/check_contract_parity.py verifies. Use --sync-mirror to refresh "
            "the gateway-local copy of the canonical document."
        )
    )
    parser.add_argument(
        "--sync-mirror",
        action="store_true",
        help="Copy the canonical contract into the gateway-local mirror.",
    )
    args = parser.parse_args()

    app = create_app()
    document = app.state.generated_openapi()
    repository_root = Path(__file__).resolve().parents[3]

    snapshot = repository_root / "contracts" / "generated" / "esb-runtime.openapi.yaml"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(
        yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    print(snapshot)

    if args.sync_mirror:
        canonical = repository_root / "contracts" / "esb-public-api.yaml"
        mirror = Path(__file__).resolve().parents[1] / "contracts" / "esb-public-api.yaml"
        mirror.parent.mkdir(parents=True, exist_ok=True)
        mirror.write_text(canonical.read_text(encoding="utf-8"), encoding="utf-8")
        print(mirror)


if __name__ == "__main__":
    main()
