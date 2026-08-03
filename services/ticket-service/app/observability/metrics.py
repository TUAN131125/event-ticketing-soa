"""Low-cardinality Prometheus metrics."""

from prometheus_client import Counter, Gauge, Histogram

REQUEST_TOTAL = Counter(
    "ticket_http_requests_total",
    "Ticket Service HTTP requests",
    ("method", "route", "status_class"),
)
REQUEST_DURATION = Histogram(
    "ticket_http_request_duration_seconds",
    "Ticket Service request duration",
    ("method", "route"),
)
COMMAND_TOTAL = Counter(
    "ticket_commands_total",
    "Ticket command outcomes",
    ("command", "result"),
)
IDEMPOTENCY_REPLAY_TOTAL = Counter(
    "ticket_idempotency_replays_total",
    "Completed command responses replayed by scope",
    ("scope",),
)
TICKETS_BY_STATUS = Gauge(
    "ticket_records", "Current ticket records by status", ("status",)
)
READINESS = Gauge("ticket_readiness", "Ticket Service readiness")
