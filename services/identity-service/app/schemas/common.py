"""Shared API envelopes and canonical public enums."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Role(StrEnum):
    CUSTOMER = "CUSTOMER"
    ADMIN = "ADMIN"
    CHECKIN_STAFF = "CHECKIN_STAFF"
    SERVICE = "SERVICE"


class ErrorDetail(ClosedModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(ClosedModel):
    correlation_id: str = Field(alias="correlationId", min_length=1, max_length=64)
    trace_id: str = Field(alias="traceId", min_length=1, max_length=64)
    error: ErrorDetail


class Health(ClosedModel):
    service: Literal["identity-service"]
    status: Literal["UP", "READY", "DRAINING", "NOT_READY"]
    version: str
