"""Schema loi dung chung."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    correlationId: str | None = None
