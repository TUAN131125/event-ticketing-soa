"""Chinh sach retry cho gui email that bai (NOT-05/06).

Da trien khai: tinh next_attempt_at theo exponential backoff va chuyen
DEAD_LETTER sau MAX_DELIVERY_ATTEMPTS lan (xem domain/rules.py,
domain/entities.py: Delivery.mark_failed()).

Con thieu: mot scheduler/worker tu dong quet cac delivery RETRY_PENDING
da qua next_attempt_at va tu goi lai (vi du Celery beat, APScheduler, hay
cron job goi POST /deliveries/{id}/retry). Trong MVP nay, retry chi xay
ra khi Admin/Ops chu dong goi POST /deliveries/{id}/retry - next_attempt_at
duoc tinh dung de mot scheduler trong tuong lai dung ngay, khong can doi
lai logic backoff.
"""

MAX_ATTEMPTS_NOTE = (
    "Xem app.domain.rules.MAX_DELIVERY_ATTEMPTS va RETRY_BACKOFF_BASE_SECONDS."
)
