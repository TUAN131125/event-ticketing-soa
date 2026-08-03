"""Strict status and WebSocket protocol models."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SafeIdentifier = Annotated[
    str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class RealtimeStatusEvent(StrictModel):
    message_id: SafeIdentifier = Field(alias="messageId")
    booking_id: SafeIdentifier = Field(alias="bookingId")
    status: Annotated[str, Field(min_length=1, max_length=40, pattern=r"^[A-Z][A-Z0-9_]{0,39}$")]
    sequence: int = Field(ge=1, le=2_147_483_647)
    occurred_at: datetime = Field(alias="occurredAt")
    correlation_id: SafeIdentifier = Field(alias="correlationId")
    message: Annotated[str, Field(min_length=1, max_length=280)]

    @field_validator("occurred_at")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurredAt must include a timezone")
        return value

    @field_validator("message")
    @classmethod
    def reject_sensitive_message(cls, value: str) -> str:
        lowered = value.lower()
        prohibited = ("bearer ", "password", "secret", "access_token", "card number", "cvv")
        if any(term in lowered for term in prohibited):
            raise ValueError("message contains prohibited sensitive content")
        if re.search(r"\b(?:\d[ -]*?){13,19}\b", value):
            raise ValueError("message contains prohibited sensitive content")
        if re.search(r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b", value):
            raise ValueError("message contains prohibited sensitive content")
        return value

    def wire(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


class ConnectedControl(StrictModel):
    type: Literal["connected"] = "connected"
    booking_id: SafeIdentifier = Field(alias="bookingId")
    heartbeat_interval_seconds: float = Field(alias="heartbeatIntervalSeconds")


class HeartbeatControl(StrictModel):
    type: Literal["heartbeat"] = "heartbeat"
    timestamp: datetime


class ResyncRequiredControl(StrictModel):
    type: Literal["resync_required"] = "resync_required"
    booking_id: SafeIdentifier = Field(alias="bookingId")
    reason: Literal["reconnect_no_replay", "sequence_gap"]
    authoritative_url: str = Field(alias="authoritativeUrl", min_length=1, max_length=512)
    expected_sequence: int | None = Field(default=None, alias="expectedSequence", ge=1)
    observed_sequence: int | None = Field(default=None, alias="observedSequence", ge=1)


class ShutdownControl(StrictModel):
    type: Literal["shutdown"] = "shutdown"
    message: Literal["Service is restarting; reconnect and resync using REST"] = (
        "Service is restarting; reconnect and resync using REST"
    )


class ProtocolErrorControl(StrictModel):
    type: Literal["protocol_error"] = "protocol_error"
    code: Literal["INVALID_MESSAGE", "MESSAGE_TOO_LARGE"]
    message: str = Field(max_length=120)


class PongMessage(StrictModel):
    type: Literal["pong"]


class AuthenticateMessage(StrictModel):
    type: Literal["authenticate"]
    ticket: Annotated[str, Field(min_length=1, max_length=4096)]


class EventIngestResponse(StrictModel):
    correlation_id: SafeIdentifier = Field(alias="correlationId")
    outcome: Literal["accepted", "duplicate", "stale", "no_subscribers"]
    broadcast: bool
    sequence_gap: bool = Field(alias="sequenceGap")


class ErrorDetail(StrictModel):
    code: str
    message: str
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(StrictModel):
    correlation_id: str = Field(alias="correlationId")
    error: ErrorDetail
