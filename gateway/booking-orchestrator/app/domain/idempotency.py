from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any


def normalized_request_hash(payload: Mapping[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def step_key(workflow_id: str, step: str) -> str:
    return hashlib.sha256(f"{workflow_id}:{step}".encode()).hexdigest()[:48]


def request_fingerprint(payload: Mapping[str, Any]) -> str:
    return normalized_request_hash(payload)
