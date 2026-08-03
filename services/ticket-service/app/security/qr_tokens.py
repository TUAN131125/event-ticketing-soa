"""Versioned HMAC QR tokens and SVG data-URI rendering."""

from __future__ import annotations

import base64
import hashlib
import hmac
from io import BytesIO

import qrcode
import qrcode.image.svg

from app.domain.exceptions import InvalidQrToken, InvalidRequest
from app.domain.rules import validate_identifier

PREFIX = "TKT1"


def create_qr_token(ticket_id: str, qr_version: int, signing_key: str) -> str:
    ticket_id = validate_identifier(ticket_id, "ticketId")
    if qr_version < 1:
        raise InvalidRequest("qrVersion must be at least 1")
    message = f"{PREFIX}.{ticket_id}.{qr_version}"
    signature = hmac.new(
        signing_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
    ).digest()
    encoded = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{message}.{encoded}"


def verify_qr_token(
    token: str,
    *,
    expected_ticket_id: str,
    expected_qr_version: int,
    signing_key: str,
) -> None:
    if not 1 <= len(token) <= 256:
        raise InvalidQrToken()
    parts = token.split(".")
    if len(parts) != 4:
        raise InvalidQrToken()
    prefix, ticket_id, raw_version, signature = parts
    try:
        version = int(raw_version)
    except ValueError as exc:
        raise InvalidQrToken() from exc
    if (
        prefix != PREFIX
        or ticket_id != expected_ticket_id
        or version != expected_qr_version
    ):
        raise InvalidQrToken()
    expected = create_qr_token(ticket_id, version, signing_key).rsplit(".", 1)[1]
    if not hmac.compare_digest(signature, expected):
        raise InvalidQrToken()


def qr_code_data_uri(token: str) -> str:
    qr = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=4,
        image_factory=qrcode.image.svg.SvgPathFillImage,
    )
    qr.add_data(token)
    qr.make(fit=True)
    image = qr.make_image()
    buffer = BytesIO()
    image.save(buffer)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"
