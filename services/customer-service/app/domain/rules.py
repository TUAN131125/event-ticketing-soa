"""Quy tac nghiep vu thuan cua Customer Service."""
import re

from app.domain.exceptions import DuplicateEmailError, InvalidIfMatchError

_IF_MATCH_PATTERN = re.compile(r'^"([0-9]+)"$')


def ensure_email_unique(existing_emails: set[str], email: str) -> None:
    """Chan tao 2 khach hang cung email.

    Day la lop kiem tra thu nhat (o tang application), giup tra loi nhanh
    va thong bao loi ro rang cho phan lon truong hop. Lop kiem tra thu hai,
    la hang rao cuoi cung, nam o tang database: cot email trong
    infrastructure/database/models.py co UNIQUE constraint that (migration
    0001), va PostgresCustomerRepository.add()/update() bat IntegrityError
    de xu ly dung ca truong hop race condition khi 2 request tao cung email
    gan nhu dong thoi (xem DOC-03 Dependability).
    """
    if email.lower() in {e.lower() for e in existing_emails}:
        raise DuplicateEmailError(email)


def parse_if_match(raw_value: str) -> int:
    """Doc header If-Match dung dinh dang contracts/openapi/
    customer-service.yaml: pattern ^"[0-9]+"$ (so nguyen bọc trong ngoac
    kep, kieu ETag). Nem InvalidIfMatchError neu sai dinh dang - middleware
    se dich thanh HTTP 422 (Unprocessable), khac voi truong hop dung dinh
    dang nhung sai gia tri (VersionConflictError -> 409 Conflict)."""
    match = _IF_MATCH_PATTERN.match(raw_value)
    if match is None:
        raise InvalidIfMatchError(raw_value)
    return int(match.group(1))
