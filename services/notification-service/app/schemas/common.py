"""Schema loi dung chung, khop voi error contract cua ESB (DOC-01)."""
from typing import Optional

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    correlationId: Optional[str] = None
