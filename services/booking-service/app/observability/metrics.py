"""Low-cardinality Prometheus metrics."""

from prometheus_client import Counter, Gauge, Histogram

REQUEST_TOTAL = Counter(
    "booking_http_requests_total",
    "Booking Service HTTP requests",
    ("method", "route", "status_class"),
)
REQUEST_DURATION = Histogram(
    "booking_http_request_duration_seconds",
    "Booking Service request duration",
    ("method", "route"),
)
COMMAND_TOTAL = Counter(
    "booking_commands_total",
    "Booking command outcomes",
    ("command", "result"),
)
IDEMPOTENCY_REPLAY_TOTAL = Counter(
    "booking_idempotency_replays_total",
    "Completed command responses replayed by scope",
    ("scope",),
)
BOOKINGS_BY_STATUS = Gauge(
    "booking_records",
    "Current booking records by status",
    ("status",),
)
READINESS = Gauge("booking_readiness", "Booking Service readiness")
