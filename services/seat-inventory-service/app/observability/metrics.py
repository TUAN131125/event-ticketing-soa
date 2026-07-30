"""Prometheus metrics for correctness, latency, retries, and expiry health."""

from prometheus_client import Counter, Gauge, Histogram

OPERATION_TOTAL = Counter(
    "seat_operation_total",
    "Seat Inventory operations by outcome",
    ("operation", "result"),
)
OPERATION_DURATION = Histogram(
    "seat_operation_duration_seconds",
    "Seat Inventory operation duration",
    ("operation",),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 5),
)
SOAP_FAULT_TOTAL = Counter(
    "seat_soap_fault_total",
    "SOAP faults by stable code and retryability",
    ("code", "retryable"),
)
IDEMPOTENCY_REPLAY_TOTAL = Counter(
    "seat_idempotency_replay_total",
    "Commands served from an idempotency record",
    ("operation",),
)
RESERVE_CONFLICT_TOTAL = Counter(
    "seat_reserve_conflict_total",
    "Reserve requests rejected because seats were unavailable",
)
EXPIRED_RESERVATIONS_TOTAL = Counter(
    "seat_expired_reservations_total",
    "Reservations released by TTL expiry",
)
EXPIRY_WORKER_UP = Gauge(
    "seat_expiry_worker_up",
    "Whether the local expiry worker loop is healthy",
)
READINESS = Gauge(
    "seat_readiness",
    "Whether the service can reach the migrated PostgreSQL schema",
)
