"""HTTP compatibility helpers for optimistic Booking concurrency."""

from __future__ import annotations

from fastapi import Response

from app.domain.entities import Booking
from app.domain.exceptions import InvalidRequest
from app.schemas.responses import BookingResponse

ETAG_RESPONSE_HEADER = {
    "ETag": {
        "description": "Current Booking resourceVersion as a quoted entity tag.",
        "schema": {"type": "string", "example": '"4"'},
    }
}
OK_WITH_ETAG = {200: {"headers": ETAG_RESPONSE_HEADER}}
CREATED_WITH_ETAG = {201: {"headers": ETAG_RESPONSE_HEADER}}


def resolve_expected_version(
    body_version: int | None,
    if_match: str | None,
) -> int:
    """Resolve old ``expectedVersion`` and canonical ``If-Match`` contracts.

    Existing clients may continue sending ``expectedVersion`` in the request
    body. New clients may send an HTTP entity tag. When both are supplied they
    must identify the same aggregate version.
    """
    header_version = _parse_if_match(if_match) if if_match is not None else None
    if body_version is None and header_version is None:
        raise InvalidRequest("expectedVersion or If-Match is required")
    if (
        body_version is not None
        and header_version is not None
        and body_version != header_version
    ):
        raise InvalidRequest("expectedVersion and If-Match must match")
    resolved = header_version if header_version is not None else body_version
    if resolved is None:
        raise InvalidRequest("expectedVersion or If-Match is required")
    return resolved


def booking_response(booking: Booking, response: Response) -> BookingResponse:
    response.headers["ETag"] = f'"{booking.resource_version}"'
    return BookingResponse.from_entity(booking)


def _parse_if_match(value: str) -> int:
    normalized = value.strip()
    if normalized.startswith("W/"):
        normalized = normalized[2:].strip()
    if len(normalized) >= 2 and normalized[0] == normalized[-1] == '"':
        normalized = normalized[1:-1]
    if not normalized.isdigit():
        raise InvalidRequest('If-Match must be an integer ETag such as "4"')
    version = int(normalized)
    if version < 1:
        raise InvalidRequest("If-Match version must be at least 1")
    return version
