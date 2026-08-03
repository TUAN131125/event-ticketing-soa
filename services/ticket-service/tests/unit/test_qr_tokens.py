import base64

import pytest

from app.domain.exceptions import InvalidQrToken
from app.security.qr_tokens import create_qr_token, qr_code_data_uri, verify_qr_token

KEY = "test-qr-signing-key-that-is-long-enough"


def test_qr_token_is_deterministic_signed_and_renderable() -> None:
    token = create_qr_token("TKT000000001", 1, KEY)
    assert token == create_qr_token("TKT000000001", 1, KEY)
    verify_qr_token(
        token,
        expected_ticket_id="TKT000000001",
        expected_qr_version=1,
        signing_key=KEY,
    )
    data_uri = qr_code_data_uri(token)
    assert data_uri.startswith("data:image/svg+xml;base64,")
    svg = base64.b64decode(data_uri.split(",", 1)[1])
    assert b"<svg" in svg


@pytest.mark.parametrize(
    ("ticket_id", "version", "key"),
    [
        ("TKT000000002", 1, KEY),
        ("TKT000000001", 2, KEY),
        ("TKT000000001", 1, "another-signing-key"),
    ],
)
def test_wrong_ticket_stale_version_and_wrong_key_are_rejected(
    ticket_id: str, version: int, key: str
) -> None:
    token = create_qr_token("TKT000000001", 1, KEY)
    with pytest.raises(InvalidQrToken):
        verify_qr_token(
            token,
            expected_ticket_id=ticket_id,
            expected_qr_version=version,
            signing_key=key,
        )


def test_tampered_and_oversized_tokens_are_rejected() -> None:
    token = create_qr_token("TKT000000001", 1, KEY)
    replacement = "A" if token[-1] != "A" else "B"
    with pytest.raises(InvalidQrToken):
        verify_qr_token(
            f"{token[:-1]}{replacement}",
            expected_ticket_id="TKT000000001",
            expected_qr_version=1,
            signing_key=KEY,
        )
    with pytest.raises(InvalidQrToken):
        verify_qr_token(
            "A" * 257,
            expected_ticket_id="TKT000000001",
            expected_qr_version=1,
            signing_key=KEY,
        )
