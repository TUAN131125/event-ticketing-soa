"""ErrorResponse/ErrorDetail - khop dung format trong OpenAPI Giai doan
5 (khac voi format cu {"error": "...", "detail": "..."} truoc day)."""

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str
    retryable: bool
    details: dict | None = None


class ErrorResponse(BaseModel):
    correlationId: str
    traceId: str | None = None
    error: ErrorDetail
