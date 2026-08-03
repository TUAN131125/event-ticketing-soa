"""Low-cardinality Prometheus metrics."""

from prometheus_client import Counter, Gauge, Histogram

REQUEST_TOTAL = Counter(
    "payment_http_requests_total",
    "Payment Service HTTP requests",
    ("method", "route", "status_class"),
)
REQUEST_DURATION = Histogram(
    "payment_http_request_duration_seconds",
    "Payment Service request duration",
    ("method", "route"),
)
COMMAND_TOTAL = Counter(
    "payment_commands_total",
    "Payment command outcomes",
    ("command", "result"),
)
IDEMPOTENCY_REPLAY_TOTAL = Counter(
    "payment_idempotency_replays_total",
    "Completed command responses replayed by scope",
    ("scope",),
)
PAYMENTS_BY_STATUS = Gauge(
    "payment_records",
    "Current payment records by status",
    ("status",),
)
READINESS = Gauge("payment_readiness", "Payment Service readiness")
