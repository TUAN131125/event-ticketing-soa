"""Schema loi dung chung."""
from typing import Optional

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    correlationId: Optional[str] = None
