"""Prometheus metrics with bounded, operational labels only."""

from prometheus_client import Counter, Gauge, Histogram

ACTIVE_CONNECTIONS = Gauge("realtime_active_websocket_connections", "Active WebSocket connections")
CONNECTION_ATTEMPTS = Counter(
    "realtime_websocket_connection_attempts_total", "WebSocket handshake attempts"
)
ACCEPTED_CONNECTIONS = Counter(
    "realtime_websocket_connections_accepted_total", "Accepted WebSocket connections"
)
REJECTED_CONNECTIONS = Counter(
    "realtime_websocket_connections_rejected_total", "Rejected WebSocket connections", ("reason",)
)
DISCONNECTS = Counter("realtime_websocket_disconnects_total", "WebSocket disconnects", ("reason",))
HEARTBEAT_TIMEOUTS = Counter(
    "realtime_websocket_heartbeat_timeouts_total", "Connections closed after idle timeout"
)
INTERNAL_EVENTS = Counter(
    "realtime_internal_events_received_total", "Internal status events received", ("outcome",)
)
EVENTS_ACCEPTED = Counter("realtime_events_accepted_total", "Status events accepted")
DUPLICATE_EVENTS = Counter("realtime_events_duplicate_total", "Duplicate status events")
STALE_EVENTS = Counter("realtime_events_stale_total", "Stale status events")
SEQUENCE_GAPS = Counter("realtime_sequence_gaps_total", "Observed sequence gaps")
BROADCAST_ATTEMPTS = Counter(
    "realtime_broadcast_attempts_total", "Broadcast attempts", ("backend",)
)
BROADCAST_FAILURES = Counter(
    "realtime_broadcast_failures_total", "Broadcast failures", ("backend",)
)
DEAD_CONNECTIONS = Counter(
    "realtime_dead_connections_removed_total", "Slow or dead connections removed", ("reason",)
)
READINESS = Gauge("realtime_readiness", "Realtime readiness")
HTTP_REQUESTS = Counter(
    "realtime_http_requests_total", "HTTP requests", ("operation", "status_class")
)
HTTP_DURATION = Histogram(
    "realtime_http_request_duration_seconds", "HTTP request duration", ("operation",)
)
