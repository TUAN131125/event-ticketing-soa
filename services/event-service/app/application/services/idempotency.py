"""Boc mot thao tac mutation bang Idempotency-Key: ESB duoc phep retry
an toan khi mat ket noi giua chung ma khong lam nghiep vu chay 2 lan
(bat buoc tren POST/PUT/publish/pause/cancel theo OpenAPI)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable

from app.domain.exceptions import IdempotencyKeyReusedError
from app.repositories.interfaces import IdempotencyRepository


def _hash_body(body: dict) -> str:
    return hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode()
    ).hexdigest()


def run_idempotent(
    idem_repo: IdempotencyRepository,
    scope: str,
    request_body: dict,
    execute: Callable[[], tuple[int, dict]],
) -> tuple[int, dict]:
    """scope phai duy nhat cho tung (operation, resource, Idempotency-Key).
    Tra ve (status_code, response_body) - lay tu cache neu da xu ly
    truoc do voi cung than request, hoac chay `execute` lan dau."""
    request_hash = _hash_body(request_body)
    cached = idem_repo.get(scope)
    if cached is not None:
        cached_hash, status_code, response_body = cached
        if cached_hash != request_hash:
            raise IdempotencyKeyReusedError(scope)
        return status_code, response_body

    status_code, response_body = execute()
    idem_repo.save(scope, request_hash, status_code, response_body)
    return status_code, response_body
