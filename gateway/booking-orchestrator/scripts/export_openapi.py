from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from app.main import create_app


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Export the OpenAPI generated from FastAPI decorators. By default this only "
            "updates the runtime snapshot used by CI. Canonical files are changed only "
            "with the explicit --update-canonical maintainer flag."
        )
    )
    parser.add_argument(
        "--update-canonical",
        action="store_true",
        help="Also update the repository canonical contract and gateway mirror.",
    )
    args = parser.parse_args()

    app = create_app()
    document = app.state.generated_openapi()
    repository_root = Path(__file__).resolve().parents[3]
    destinations = [
        repository_root / "contracts" / "generated" / "esb-runtime.openapi.yaml",
    ]
    if args.update_canonical:
        destinations.extend(
            [
                repository_root / "contracts" / "esb-public-api.yaml",
                Path(__file__).resolve().parents[1] / "contracts" / "esb-public-api.yaml",
            ]
        )

    rendered = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
    for destination in destinations:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered, encoding="utf-8")
        print(destination)


if __name__ == "__main__":
    main()
