"""Dead-letter store toi gian: giu lai cac lan gui that bai de xem xet sau.

Chua trien khai: retry tu dong doc lai dead-letter (delivery/retry.py).
Trong MVP, dead-letter chi phuc vu muc dich quan sat/demo ("Notification
loi nhung Booking khong rollback" - kich ban demo da thong nhat truoc do).
"""


class DeadLetterStore:
    def __init__(self) -> None:
        self._items: list[dict] = []

    def add(self, payload: dict, error: str) -> None:
        self._items.append({"payload": payload, "error": error})

    def list_all(self) -> list[dict]:
        return list(self._items)
