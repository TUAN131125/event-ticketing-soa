"""Quy tac nghiep vu thuan cua Notification Service."""
from app.domain.exceptions import DuplicateCorrelationError


def ensure_correlation_not_duplicate(already_exists: bool, correlation_id: str) -> None:
    """Chan gui trung 1 email cho cung 1 correlationId (vd ESB retry webhook
    sau timeout du that ra da xu ly thanh cong lan truoc).

    `already_exists` do repo.exists_by_correlation_id() tra ve - kiem tra
    nay o tang application/domain (truoc khi ghi) giup tra ve nhanh ma
    khong can cho transaction that bai trong da so truong hop. Hang rao
    cuoi cung, dam bao dung ke ca khi co 2 request trung correlationId toi
    gan nhu dong thoi, la UNIQUE constraint tren cot correlation_id (xem
    migrations/versions/0001_initial_schema.py), duoc
    PostgresDeliveryRepository dich lai thanh loi domain nay khi insert
    that bai.
    """
    if already_exists:
        raise DuplicateCorrelationError(correlation_id)
