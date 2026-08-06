from __future__ import annotations
import hashlib, json
from typing import Any
from .errors import Conflict

def request_hash(payload: dict[str, Any]) -> str:
    canonical=json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()

def assert_replay_compatible(expected: str, actual: str) -> None:
    if expected != actual:
        raise Conflict('IDEMPOTENCY_KEY_REUSED','Idempotency-Key was already used for a different request')
