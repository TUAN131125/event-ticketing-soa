from datetime import UTC, datetime

import pytest

from app.api.v1.provider import _compatible_header
from app.domain.exceptions import ProviderSignatureInvalid
from app.security.provider_callback import callback_signature, verify_callback


def test_callback_signature_accepts_canonical_hmac_and_prefix() -> None:
    now = datetime(2026, 8, 6, 2, 0, tzinfo=UTC)
    timestamp = str(int(now.timestamp()))
    body = b'{"eventId":"evt-1"}'
    signature = callback_signature("secret", timestamp, body)

    parsed = verify_callback(
        secret="secret",
        timestamp=timestamp,
        signature=f"sha256={signature}",
        body=body,
        replay_window_seconds=300,
        max_body_bytes=1024,
        now=now,
    )

    assert parsed == now


def test_callback_rejects_invalid_signature_old_timestamp_and_large_body() -> None:
    now = datetime(2026, 8, 6, 2, 0, tzinfo=UTC)
    timestamp = str(int(now.timestamp()))
    with pytest.raises(ProviderSignatureInvalid):
        verify_callback(
            secret="secret",
            timestamp=timestamp,
            signature="invalid",
            body=b"{}",
            replay_window_seconds=300,
            max_body_bytes=1024,
            now=now,
        )
    old_timestamp = str(int(now.timestamp()) - 301)
    old_signature = callback_signature("secret", old_timestamp, b"{}")
    with pytest.raises(ProviderSignatureInvalid, match="replay window"):
        verify_callback(
            secret="secret",
            timestamp=old_timestamp,
            signature=old_signature,
            body=b"{}",
            replay_window_seconds=300,
            max_body_bytes=1024,
            now=now,
        )
    with pytest.raises(ProviderSignatureInvalid, match="too large"):
        verify_callback(
            secret="secret",
            timestamp=timestamp,
            signature="ignored",
            body=b"x" * 1025,
            replay_window_seconds=300,
            max_body_bytes=1024,
            now=now,
        )


def test_callback_header_aliases_are_compatible_but_cannot_conflict() -> None:
    assert _compatible_header("1", None, name="timestamp") == "1"
    assert _compatible_header(None, "1", name="timestamp") == "1"
    assert _compatible_header("1", "1", name="timestamp") == "1"
    with pytest.raises(ProviderSignatureInvalid, match="Conflicting"):
        _compatible_header("1", "2", name="timestamp")
