"""Shared API envelopes."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ErrorDetail(ClosedModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(ClosedModel):
    correlation_id: str = Field(alias="correlationId")
    trace_id: str = Field(alias="traceId")
    error: ErrorDetail


class HealthResponse(ClosedModel):
    service: str
    status: str
    version: str
