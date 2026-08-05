"""Reservation expiry worker safe to run in every service replica."""

from __future__ import annotations

import asyncio
import logging

from app.application.common import RequestContext
from app.application.executor import execute_database_operation
from app.application.expire_reservations import ExpiryResult, expire_reservations
from app.config import Settings
from app.observability.metrics import (
    EXPIRED_RESERVATIONS_TOTAL,
    EXPIRY_WORKER_UP,
)
from app.observability.tracing import new_correlation_id

LOGGER = logging.getLogger(__name__)


def run_expiry_once(settings: Settings) -> ExpiryResult:
    context = RequestContext(
        correlation_id=new_correlation_id(),
        caller_service="seat-expiry-worker",
        schema_version="1",
    )
    return execute_database_operation(
        settings,
        lambda session: expire_reservations(
            session,
            settings,
            context,
            batch_size=settings.expiry_batch_size,
        ),
    )


async def expiry_loop(settings: Settings, stop_event: asyncio.Event) -> None:
    EXPIRY_WORKER_UP.set(1)
    try:
        while not stop_event.is_set():
            try:
                result = await asyncio.to_thread(run_expiry_once, settings)
                if result.expired_count:
                    EXPIRED_RESERVATIONS_TOTAL.inc(result.expired_count)
                    LOGGER.info(
                        "Expired reservations released",
                        extra={
                            "operation": "ExpireReservations",
                            "result": "SUCCESS",
                            "seat_count": result.expired_count,
                        },
                    )
            except Exception:
                EXPIRY_WORKER_UP.set(0)
                LOGGER.exception(
                    "Expiry worker iteration failed",
                    extra={"operation": "ExpireReservations", "result": "ERROR"},
                )
            try:
                await asyncio.wait_for(
                    stop_event.wait(), timeout=settings.expiry_poll_seconds
                )
            except TimeoutError:
                EXPIRY_WORKER_UP.set(1)
    finally:
        EXPIRY_WORKER_UP.set(0)
