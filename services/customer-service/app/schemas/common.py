"""Schema loi dung chung, khop voi error contract cua ESB (DOC-01)."""

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    correlationId: str | None = None
