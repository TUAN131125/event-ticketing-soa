"""Stable domain enumerations."""

from enum import StrEnum


class UserStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class RoleName(StrEnum):
    CUSTOMER = "CUSTOMER"
    ADMIN = "ADMIN"
    CHECKIN_STAFF = "CHECKIN_STAFF"
    SERVICE = "SERVICE"


class RoleAction(StrEnum):
    ASSIGN = "ASSIGN"
    REVOKE = "REVOKE"


class AuditResult(StrEnum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    NO_CHANGE = "NO_CHANGE"
