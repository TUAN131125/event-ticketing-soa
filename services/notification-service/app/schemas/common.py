"""Schema loi dung chung - khop CHINH XAC dinh dang trong hop dong
(Giai doan 5, contracts/openapi/notification-service.yaml #/components/schemas/ErrorResponse)."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9_]+$")
    message: str = Field(max_length=500)
    retryable: bool
    details: Optional[dict] = None


class ErrorResponse(BaseModel):
    correlationId: str = Field(min_length=1, max_length=64)
    traceId: Optional[str] = None
    error: ErrorDetail
