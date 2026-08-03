"""Authenticated, authorized booking WebSocket endpoint."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.errors import Unauthenticated
from app.observability.metrics import (
    ACCEPTED_CONNECTIONS,
    CONNECTION_ATTEMPTS,
    DISCONNECTS,
    REJECTED_CONNECTIONS,
)
from app.observability.tracing import bind, reset, safe_id, trace_id
from app.schemas.messages import (
    ConnectedControl,
    PongMessage,
    ProtocolErrorControl,
    ResyncRequiredControl,
)
from app.security.token_validation import websocket_token
from app.websocket.subscriptions import ConnectionLimitExceeded

LOGGER = logging.getLogger("realtime.websocket")

CLOSE_UNAUTHENTICATED = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_INVALID_ORIGIN = 4408
CLOSE_RATE_LIMITED = 4429
CLOSE_PROTOCOL_ERROR = 4400
CLOSE_SERVER_SHUTDOWN = 1012


def _booking_ref(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()[:12]


async def _reject(websocket: WebSocket, code: int, reason: str, metric_reason: str) -> None:
    REJECTED_CONNECTIONS.labels(metric_reason).inc()
    await websocket.close(code=code, reason=reason)


def create_websocket_router() -> APIRouter:
    router = APIRouter()

    @router.websocket("/ws/bookings/{booking_id}")
    async def booking_status(websocket: WebSocket, booking_id: str) -> None:
        started = time.perf_counter()
        CONNECTION_ATTEMPTS.inc()
        state = websocket.app.state
        settings = state.settings
        client_ip = websocket.client.host if websocket.client else "unknown"
        correlation_id = safe_id(websocket.headers.get("x-correlation-id"))
        tokens = bind(correlation_id, trace_id(websocket.headers.get("traceparent")))
        connection = None
        heartbeat_task: asyncio.Task[None] | None = None
        outcome = "rejected"
        try:
            if state.draining or state.connection_manager.draining:
                await _reject(websocket, CLOSE_SERVER_SHUTDOWN, "service is draining", "draining")
                return
            origin = websocket.headers.get("origin")
            if origin is None or origin.rstrip("/") not in settings.allowed_ws_origins:
                await _reject(websocket, CLOSE_INVALID_ORIGIN, "origin is not allowed", "origin")
                return
            if not await state.handshake_limiter.allow(client_ip):
                await _reject(
                    websocket, CLOSE_RATE_LIMITED, "handshake rate limit exceeded", "rate_limit"
                )
                return
            token, subprotocol = websocket_token(
                websocket.headers, websocket.query_params, allow_query=settings.allow_query_token
            )
            if token is None:
                await _reject(
                    websocket, CLOSE_UNAUTHENTICATED, "authentication required", "unauthenticated"
                )
                return
            try:
                principal = await state.token_validator.validate(token)
            except Unauthenticated:
                await _reject(
                    websocket, CLOSE_UNAUTHENTICATED, "authentication failed", "unauthenticated"
                )
                return
            if not await state.access_checker.can_subscribe(principal, booking_id, correlation_id):
                await _reject(websocket, CLOSE_FORBIDDEN, "booking access denied", "forbidden")
                return
            try:
                connection = await state.connection_manager.register(
                    websocket,
                    booking_id=booking_id,
                    principal_id=principal.subject,
                    client_ip=client_ip,
                    subprotocol=subprotocol,
                )
            except ConnectionLimitExceeded as exc:
                code = CLOSE_SERVER_SHUTDOWN if exc.reason == "draining" else CLOSE_RATE_LIMITED
                await _reject(websocket, code, "connection unavailable", "connection_limit")
                return
            ACCEPTED_CONNECTIONS.inc()
            outcome = "accepted"
            await state.connection_manager.send(
                connection,
                ConnectedControl(
                    bookingId=booking_id,
                    heartbeatIntervalSeconds=settings.heartbeat_interval_seconds,
                ).model_dump(by_alias=True, mode="json"),
            )
            last_sequence_raw = websocket.query_params.get("lastSequence")
            if last_sequence_raw is not None:
                try:
                    last_sequence = int(last_sequence_raw)
                    if last_sequence < 0:
                        raise ValueError
                except ValueError:
                    control = ProtocolErrorControl(
                        code="INVALID_MESSAGE",
                        message="lastSequence must be a non-negative integer",
                    )
                    await state.connection_manager.send(connection, control.model_dump(mode="json"))
                    await websocket.close(code=CLOSE_PROTOCOL_ERROR, reason="invalid lastSequence")
                    return
                resync = ResyncRequiredControl(
                    bookingId=booking_id,
                    reason="reconnect_no_replay",
                    authoritativeUrl=settings.authoritative_booking_url_template.replace(
                        "{bookingId}", booking_id
                    ),
                    observedSequence=last_sequence if last_sequence > 0 else None,
                )
                await state.connection_manager.send(
                    connection, resync.model_dump(by_alias=True, mode="json")
                )
            heartbeat_task = asyncio.create_task(
                state.heartbeat.run(connection), name=f"heartbeat-{connection.id}"
            )
            while not connection.closed:
                raw = await websocket.receive_text()
                await state.connection_manager.touch(connection)
                if len(raw.encode("utf-8")) > settings.max_client_message_bytes:
                    control = ProtocolErrorControl(
                        code="MESSAGE_TOO_LARGE",
                        message="Client message exceeds the configured limit",
                    )
                    await state.connection_manager.send(connection, control.model_dump(mode="json"))
                    await websocket.close(code=CLOSE_PROTOCOL_ERROR, reason="message too large")
                    return
                try:
                    PongMessage.model_validate_json(raw)
                except ValidationError:
                    control = ProtocolErrorControl(
                        code="INVALID_MESSAGE", message="Only the pong control message is accepted"
                    )
                    await state.connection_manager.send(connection, control.model_dump(mode="json"))
                    await websocket.close(code=CLOSE_PROTOCOL_ERROR, reason="invalid message")
                    return
        except WebSocketDisconnect:
            DISCONNECTS.labels("client").inc()
        finally:
            if heartbeat_task is not None:
                heartbeat_task.cancel()
                await asyncio.gather(heartbeat_task, return_exceptions=True)
            if connection is not None:
                await state.connection_manager.unregister(connection)
            stats = await state.connection_manager.stats()
            LOGGER.info(
                "WebSocket lifecycle completed",
                extra={
                    "operation": "booking_subscription",
                    "outcome": outcome,
                    "durationMs": round((time.perf_counter() - started) * 1000, 2),
                    "bookingRef": _booking_ref(booking_id),
                    "activeConnections": stats["activeConnections"],
                },
            )
            reset(tokens)

    return router
