"""Loi thuoc domain - khong phu thuoc HTTP status code.

Ghi chu: DuplicateCorrelationError KHONG duoc dua len thanh loi HTTP (xem
middleware/error_handler.py - service nay khong dang ky handler cho no).
Webhook la endpoint duoc ESB goi lai (retry) nen theo dung hop dong idempotent
webhook: van tra 200 kem status "DUPLICATE_IGNORED", khong tra 4xx/5xx - neu
khong ESB se hieu nham la loi va retry vo han.
"""


class DuplicateCorrelationError(Exception):
    def __init__(self, correlation_id: str):
        self.correlation_id = correlation_id
        super().__init__(f"Da xu ly correlationId nay roi: {correlation_id}")


class DeliveryNotFoundError(Exception):
    def __init__(self, delivery_id: str):
        self.delivery_id = delivery_id
        super().__init__(f"Khong tim thay ban ghi gui thong bao: {delivery_id}")
