from __future__ import annotations

import sys
from pathlib import Path

GATEWAY_ROOT = Path(__file__).resolve().parents[3] / "gateway" / "booking-orchestrator"
sys.path.insert(0, str(GATEWAY_ROOT))
