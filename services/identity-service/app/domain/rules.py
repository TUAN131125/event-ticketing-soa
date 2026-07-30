"""Pure domain validation rules."""

from __future__ import annotations

import re

from email_validator import EmailNotValidError, validate_email

from app.domain.exceptions import InvalidRequest

_UPPER = re.compile(r"[A-Z]")
_LOWER = re.compile(r"[a-z]")
_DIGIT = re.compile(r"\d")
_SYMBOL = re.compile(r"[^A-Za-z0-9]")


def normalize_email(value: str) -> tuple[str, str]:
    try:
        result = validate_email(value.strip(), check_deliverability=False)
    except EmailNotValidError as exc:
        raise InvalidRequest("Email address is invalid") from exc
    normalized = result.normalized.lower()
    return result.normalized, normalized


def validate_password(password: str) -> None:
    if not 12 <= len(password) <= 128:
        raise InvalidRequest("Password must contain between 12 and 128 characters")
    if not (
        _UPPER.search(password)
        and _LOWER.search(password)
        and _DIGIT.search(password)
        and _SYMBOL.search(password)
    ):
        raise InvalidRequest(
            "Password must include upper-case, lower-case, number and symbol"
        )
