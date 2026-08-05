from __future__ import annotations

import io
import json
import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from app.middleware.correlation_id import context_middleware
from app.middleware.logging import LOGGER, access_log_middleware
from app.observability.logs import JsonFormatter


def test_access_log_keeps_correlation_context_until_log_is_written():
    application = FastAPI()
    application.add_middleware(
        BaseHTTPMiddleware,
        dispatch=access_log_middleware,
    )
    application.add_middleware(
        BaseHTTPMiddleware,
        dispatch=context_middleware,
    )

    @application.get("/probe", operation_id="probe")
    def probe() -> dict[str, bool]:
        return {"ok": True}

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    try:
        response = TestClient(application).get(
            "/probe",
            headers={"X-Correlation-ID": "corr-test-123456"},
        )
    finally:
        LOGGER.removeHandler(handler)

    assert response.status_code == 200
    log = json.loads(stream.getvalue().strip().splitlines()[-1])
    assert log["correlationId"] == "corr-test-123456"
    assert log["operation"] == "probe"
