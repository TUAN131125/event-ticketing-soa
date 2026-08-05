"""Prometheus metrics with bounded labels."""

from prometheus_client import Counter, Gauge, Histogram

REQUESTS = Counter(
    "identity_http_requests_total",
    "Identity HTTP requests",
    ("operation", "status"),
)
REQUEST_DURATION = Histogram(
    "identity_http_request_duration_seconds",
    "Identity HTTP request latency",
    ("operation",),
)
AUTH_EVENTS = Counter(
    "identity_auth_events_total",
    "Authentication and authorization events",
    ("event", "result"),
)
ERROR_RESPONSES = Counter(
    "identity_error_responses_total",
    "Identity API error responses",
    ("code", "status"),
)
ACTIVE_REFRESH_SESSIONS = Gauge(
    "identity_active_refresh_sessions",
    "Active, unexpired refresh sessions",
)
READINESS = Gauge("identity_readiness", "Identity readiness state")
