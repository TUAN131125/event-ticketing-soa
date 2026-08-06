"""Standalone outbox relay process.

Run alongside the API with `python -m app.workers.outbox_relay`. It is a separate
process on purpose: publishing must not share a request thread, and the relay can
be scaled or restarted without touching API availability.
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
from types import FrameType

from app.application.outbox import OutboxRelay, create_publisher
from app.config import Settings, get_settings
from app.infrastructure.database.session import dispose_engine, get_session_factory
from app.observability.logs import configure_logging

LOGGER = logging.getLogger("payment.outbox")


def _install_signal_handlers(stopping: threading.Event) -> None:
    def handle(_signal: int, _frame: FrameType | None) -> None:
        stopping.set()

    for name in ("SIGTERM", "SIGINT"):
        received = getattr(signal, name, None)
        if received is not None:
            signal.signal(received, handle)


def run(settings: Settings, stopping: threading.Event) -> None:
    """Poll until asked to stop, draining the outbox on every tick."""
    relay = OutboxRelay(
        settings, get_session_factory(settings), create_publisher(settings)
    )
    LOGGER.info(
        "Outbox relay started",
        extra={
            "operation": "outbox.start",
            "result": "RUNNING",
            "webhook_enabled": settings.outbox_webhook_enabled,
        },
    )
    while not stopping.is_set():
        try:
            result = relay.run_once()
            relay.refresh_backlog_gauges()
        except Exception:
            # An unexpected failure must stay loud rather than silently stall
            # delivery; the next tick retries the same event.
            LOGGER.exception(
                "Outbox relay tick failed",
                extra={"operation": "outbox.tick", "result": "ERROR"},
            )
            stopping.wait(settings.outbox_poll_seconds)
            continue
        if result.processed == 0:
            stopping.wait(settings.outbox_poll_seconds)
    LOGGER.info("Outbox relay stopped", extra={"operation": "outbox.stop"})


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    stopping = threading.Event()
    _install_signal_handlers(stopping)
    try:
        run(settings, stopping)
    finally:
        dispose_engine(settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
