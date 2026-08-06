"""Standalone worker for PAY-08 UNKNOWN-payment reconciliation."""

from __future__ import annotations

import logging
import signal
import sys
import threading
from types import FrameType

from app.application.service import PaymentService
from app.config import Settings, get_settings
from app.domain.exceptions import PaymentError, ProviderUnavailable
from app.domain.value_objects import RequestContext
from app.infrastructure.database.session import dispose_engine, get_session_factory
from app.observability.logs import configure_logging

LOGGER = logging.getLogger("payment.reconciliation")


def _install_signal_handlers(stopping: threading.Event) -> None:
    def handle(_signal: int, _frame: FrameType | None) -> None:
        stopping.set()

    for name in ("SIGTERM", "SIGINT"):
        received = getattr(signal, name, None)
        if received is not None:
            signal.signal(received, handle)


def run(settings: Settings, stopping: threading.Event) -> None:
    service = PaymentService(settings, get_session_factory(settings))
    LOGGER.info(
        "Payment reconciliation worker started",
        extra={"operation": "reconciliation.start", "result": "RUNNING"},
    )
    while not stopping.is_set():
        due = service.due_reconciliations()
        if not due:
            stopping.wait(settings.provider_reconciliation_poll_seconds)
            continue
        for payment_id, version in due:
            if stopping.is_set():
                break
            key = f"reconcile-{payment_id}-{version}"
            context = RequestContext(
                correlation_id=key,
                caller_service="payment-reconciliation-worker",
            )
            try:
                service.reconcile(
                    context,
                    idempotency_key=key,
                    payment_id=payment_id,
                    provider_status=None,
                    provider_reference=None,
                    provider_refund_reference=None,
                    observed_refunded_amount=None,
                    failure_code=None,
                    reason=None,
                    expected_version=version,
                )
            except ProviderUnavailable:
                LOGGER.warning(
                    "Provider outcome is still unavailable",
                    extra={
                        "operation": "reconciliation.payment",
                        "result": "DEFERRED",
                        "payment_id": payment_id,
                    },
                )
            except PaymentError as error:
                # A callback may have resolved the payment after the batch was read.
                # State/version conflicts are therefore expected and safe to skip.
                LOGGER.info(
                    "Reconciliation candidate changed before processing",
                    extra={
                        "operation": "reconciliation.payment",
                        "result": "SKIPPED",
                        "payment_id": payment_id,
                        "error_code": error.code,
                    },
                )
    LOGGER.info(
        "Payment reconciliation worker stopped",
        extra={"operation": "reconciliation.stop", "result": "STOPPED"},
    )


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
