"""Xac thuc chu ky webhook that (NOT-02, Muc 8 "Bao mat va quyen rieng
tu" cua dac ta SVC-08) - thay the ban placeholder truoc day.

Dinh dang header (theo vi du hop dong Muc 3.2):
    X-Signature: sha256=<hmac-sha256(shared_secret, raw_request_body) dang hex>

Dung hmac.compare_digest de tranh timing attack. Bi tu choi (401
WEBHOOK_SIGNATURE_INVALID) neu thieu header, sai dinh dang, hoac khong
khop.
"""
from __future__ import annotations

import hashlib
import hmac

from app.domain.exceptions import WebhookSignatureInvalidError

SIGNATURE_HEADER = "X-Signature"
SIGNATURE_PREFIX = "sha256="


def verify_signature(raw_body: bytes, signature_header: str | None, shared_secret: str) -> None:
    if not signature_header or not signature_header.startswith(SIGNATURE_PREFIX):
        raise WebhookSignatureInvalidError(
            f"Thieu hoac sai dinh dang header {SIGNATURE_HEADER}"
        )
    provided = signature_header[len(SIGNATURE_PREFIX):].strip()
    expected = hmac.new(shared_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(provided, expected):
        raise WebhookSignatureInvalidError("Chu ky khong khop")
