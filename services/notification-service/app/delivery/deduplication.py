"""Chong xu ly trung 1 event (idempotency o muc co ban).

Ghi chu pham vi: dung set trong bo nho theo correlationId. Neu Notification
Service chay nhieu instance (redundancy that), set nay can chuyen sang
Redis dung chung de cac instance thay duoc trang thai cua nhau - hien
chua can thiet cho MVP mot instance.
"""


class DeduplicationStore:
    def __init__(self) -> None:
        self._seen: set[str] = set()

    def is_duplicate(self, correlation_id: str) -> bool:
        return correlation_id in self._seen

    def mark_processed(self, correlation_id: str) -> None:
        self._seen.add(correlation_id)
