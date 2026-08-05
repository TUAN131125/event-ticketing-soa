"""Quy tac nghiep vu thuan cua Customer Service."""

from app.domain.exceptions import DuplicateEmailError


def ensure_email_unique(existing_emails: set[str], email: str) -> None:
    """Chan tao 2 khach hang cung email.

    Ghi chu pham vi: kiem tra o muc application/domain (in-memory set), chua
    co unique constraint that o database vi MVP dang dung in-memory
    repository. Khi chuyen sang PostgreSQL that, can them UNIQUE constraint
    tren cot email de dam bao integrity ngay ca khi co nhieu instance chay
    dong thoi (xem DOC-03 Dependability).
    """
    if email.lower() in {e.lower() for e in existing_emails}:
        raise DuplicateEmailError(email)
