"""Pydantic request schema - khop CHINH XAC hop dong (Giai doan 5).

Ten truong giu camelCase de khop dung EventEnvelope/TemplateUpdate trong
OpenAPI, khong doi sang snake_case noi bo.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eventId: str
    eventType: str
    schemaVersion: int = Field(ge=1)
    occurredAt: str
    correlationId: str
    aggregateId: str
    data: dict


class TemplateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(max_length=200)
    body: str = Field(max_length=10000)
