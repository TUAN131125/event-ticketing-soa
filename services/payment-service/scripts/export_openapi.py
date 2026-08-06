"""Export the runtime OpenAPI contract deterministically."""
from pathlib import Path
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import create_app  # noqa: E402
from tests.factories import build_settings  # noqa: E402

path = ROOT / "contracts" / "openapi" / "payment-service.yaml"
path.parent.mkdir(parents=True, exist_ok=True)
schema = create_app(build_settings()).openapi()
path.write_text(
    yaml.safe_dump(schema, sort_keys=False, allow_unicode=True),
    encoding="utf-8",
)
print(path)
