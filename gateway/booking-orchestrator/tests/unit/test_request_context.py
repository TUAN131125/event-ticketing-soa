from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.router import request_context


@pytest.mark.asyncio
async def test_request_context_uses_middleware_correlation_state() -> None:
    request = SimpleNamespace(
        headers={},
        state=SimpleNamespace(
            correlation_id="corr-001",
            trace_id="1" * 32,
            deadline=123.0,
        ),
        app=SimpleNamespace(
            state=SimpleNamespace(
                container=SimpleNamespace(auth=None),
            )
        ),
    )

    context = await request_context(request, optional_auth=True)
    assert context.correlation_id == "corr-001"
    assert context.trace_id == "1" * 32
    assert context.principal.subject == "anonymous"
