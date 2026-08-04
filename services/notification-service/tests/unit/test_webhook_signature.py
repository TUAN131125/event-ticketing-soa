"""Unit test cho security/webhook_signature.py (NOT-02)."""
import hashlib
import hmac

import pytest

from app.domain.exceptions import WebhookSignatureInvalidError
from app.security.webhook_signature import verify_signature

SECRET = "test-secret"


def _sign(body: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def test_valid_signature_passes() -> None:
    body = b'{"eventId":"evt-1"}'
    verify_signature(body, _sign(body), SECRET)  # khong nem loi la pass


def test_missing_signature_header_rejected() -> None:
    with pytest.raises(WebhookSignatureInvalidError):
        verify_signature(b"{}", None, SECRET)


def test_wrong_prefix_rejected() -> None:
    with pytest.raises(WebhookSignatureInvalidError):
        verify_signature(b"{}", "sha1=abcd", SECRET)


def test_tampered_body_rejected() -> None:
    body = b'{"eventId":"evt-1"}'
    signature = _sign(body)
    tampered_body = b'{"eventId":"evt-2"}'
    with pytest.raises(WebhookSignatureInvalidError):
        verify_signature(tampered_body, signature, SECRET)


def test_wrong_secret_rejected() -> None:
    body = b'{"eventId":"evt-1"}'
    signature = _sign(body)
    with pytest.raises(WebhookSignatureInvalidError):
        verify_signature(body, signature, "other-secret")
