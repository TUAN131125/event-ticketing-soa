from __future__ import annotations

import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
GATEWAY_ROOT = REPOSITORY_ROOT / "gateway" / "booking-orchestrator"
UNIT_HELPERS = REPOSITORY_ROOT / "tests" / "unit" / "esb"
sys.path.insert(0, str(GATEWAY_ROOT))
sys.path.insert(0, str(UNIT_HELPERS))
