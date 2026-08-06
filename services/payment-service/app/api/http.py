"""HTTP compatibility helpers for optimistic concurrency and ETags."""

from __future__ import annotations

import re

from fastapi import Response

from app.domain.exceptions import InvalidRequest

ETAG = re.compile(r'^(?:W/)?"?(\d+)"?$')


def resolve_expected_version(
    body_version: int | None,
    if_match: str | None,
) -> int:
    header_version: int | None = None
    if if_match is not None:
        match = ETAG.fullmatch(if_match.strip())
        if match is None:
            raise InvalidRequest('If-Match must contain a numeric ETag such as "3"')
        header_version = int(match.group(1))
    if body_version is None and header_version is None:
        raise InvalidRequest("expectedVersion or If-Match is required")
    if (
        body_version is not None
        and header_version is not None
        and body_version != header_version
    ):
        raise InvalidRequest("expectedVersion and If-Match do not match")
    return body_version if body_version is not None else int(header_version)


def set_etag(response: Response, resource_version: int) -> None:
    response.headers["ETag"] = f'"{resource_version}"'
