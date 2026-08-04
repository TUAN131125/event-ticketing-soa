"""Idempotency trong Notification Service - 3 co che khac nhau tuy layer:

1. NOT-01/02 nhan webhook: eventId la PRIMARY KEY notification.inbound_events
   (xem domain/rules.py, infrastructure/database/repositories.py). Day la
   co che chinh, ben vung qua restart.
2. NOT-05/08 retry thu cong: KHONG dung bang idempotency_records rieng
   (SQL baseline Giai doan 5 khong dinh nghia notification.idempotency_records
   nhu cac schema khac). An toan idempotent den tu trang thai nghiep vu:
   chi retry duoc khi delivery dang RETRY_PENDING/DEAD_LETTER, retry vao
   DELIVERED se bi tu choi 409 (xem domain/rules.py: ensure_delivery_retryable).
   Header Idempotency-Key van bat buoc theo hop dong nhung hien chi duoc
   validate su ton tai, chua co ledger luu response de replay y het.
3. NOT-09 template: optimistic concurrency qua If-Match/resource_version
   (giong ETag) dam nhiem vai tro tuong tu idempotency cho PUT.
"""
