"""Strict status and WebSocket protocol models."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

SafeIdentifier = Annotated[
    str, Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class RealtimeStatusEvent(StrictModel):
    message_id: SafeIdentifier = Field(alias="messageId")
    booking_id: SafeIdentifier = Field(alias="bookingId")
    status: Literal[
        "PENDING",
        "SEAT_RESERVED",
        "PAYMENT_PROCESSING",
        "CONFIRMED",
        "FAILED",
        "CANCELLED",
        "COMPENSATION_PENDING",
    ]
    sequence: int = Field(ge=1, le=2_147_483_647)
    occurred_at: datetime = Field(alias="occurredAt")
    correlation_id: SafeIdentifier = Field(alias="correlationId")
    message: Annotated[str, Field(max_length=300)] | None = None

    @field_validator("occurred_at")
    @classmethod
    def timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("occurredAt must include a timezone")
        return value

    @field_validator("message")
    @classmethod
    def reject_sensitive_message(cls, value: str | None) -> str | None:
        if value is None:
            return None
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


class AuthenticatedControl(StrictModel):
    type: Literal["authenticated"] = "authenticated"
    booking_id: SafeIdentifier = Field(alias="bookingId")
    authenticated_at: datetime = Field(alias="authenticatedAt")


class HeartbeatControl(StrictModel):
    type: Literal["heartbeat"] = "heartbeat"
    heartbeat_id: SafeIdentifier = Field(default_factory=lambda: str(uuid4()), alias="heartbeatId")
    sent_at: datetime = Field(alias="sentAt")


class ResyncRequiredControl(StrictModel):
    type: Literal["resync_required"] = "resync_required"
    booking_id: SafeIdentifier = Field(alias="bookingId")
    reason: Literal["reconnect", "sequence_gap", "history_unavailable"]
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


class HeartbeatAckMessage(StrictModel):
    type: Literal["heartbeat_ack"]
    heartbeat_id: SafeIdentifier = Field(alias="heartbeatId")


class SubscribeMessage(StrictModel):
    type: Literal["subscribe"]
    booking_id: SafeIdentifier = Field(alias="bookingId")
    last_sequence: int | None = Field(default=None, alias="lastSequence", ge=0)


class UnsubscribeMessage(StrictModel):
    type: Literal["unsubscribe"]
    booking_id: SafeIdentifier = Field(alias="bookingId")


class AuthenticateMessage(StrictModel):
    type: Literal["authenticate"]
    ticket: Annotated[str, Field(min_length=1, max_length=4096)]


class EventIngestResponse(StrictModel):
    correlation_id: SafeIdentifier = Field(alias="correlationId")
    outcome: Literal["ACCEPTED", "DUPLICATE", "STALE"]
    message_id: SafeIdentifier = Field(alias="messageId")
    booking_id: SafeIdentifier = Field(alias="bookingId")
    sequence: int = Field(ge=1)


class ConnectionHealthResponse(StrictModel):
    status: Literal["UP", "DEGRADED"]
    active_connections: int = Field(alias="activeConnections", ge=0)
    active_booking_channels: int = Field(alias="activeBookingChannels", ge=0)
    broadcast_backend: Literal["memory", "redis"] = Field(alias="broadcastBackend")
    backend_available: bool = Field(alias="backendAvailable")
    draining: bool


class ErrorDetail(StrictModel):
    code: str
    message: str
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(StrictModel):
    correlation_id: str = Field(alias="correlationId")
    error: ErrorDetail
