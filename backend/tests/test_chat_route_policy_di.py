"""Auth-path tests for the DI evaluate_policy wiring on chat routes.

The /chat and /chat/stream routes were switched from the standalone
``evaluate_policy`` (which opened its own pooled DB connection) to the DI
``get_evaluate_policy`` dependency (which reuses the request's connection).
These tests assert the permission gate still enforces access correctly through
the DI path: a deny → 403, an allow → reaches the engine.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import (
    get_current_active_user,
    get_evaluate_policy,
    get_rag_engine,
)
from app.api.routes.chat import router


def _make_client(*, allow: bool) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api")

    mock_user = {"id": 1, "username": "testuser", "role": "member"}
    app.dependency_overrides[get_current_active_user] = lambda: mock_user

    # Override the DI policy dependency with an evaluate() that grants/denies.
    async def _evaluate(*_args, **_kwargs) -> bool:
        return allow

    app.dependency_overrides[get_evaluate_policy] = lambda: _evaluate

    mock_rag = MagicMock()

    async def mock_query(*_args, **_kwargs):
        yield {"type": "content", "content": "Test response"}
        yield {"type": "done", "sources": [], "memories_used": []}

    mock_rag.query = mock_query
    app.dependency_overrides[get_rag_engine] = lambda: mock_rag

    return TestClient(app)


class TestChatStreamPolicyDI:
    def test_stream_denied_returns_403(self):
        """DI evaluate returning False must produce a 403 (no engine call)."""
        client = _make_client(allow=False)
        resp = client.post(
            "/api/chat/stream",
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "vault_id": 5,
            },
        )
        assert resp.status_code == 403
        assert "No read access" in resp.text

    def test_stream_allowed_reaches_engine(self):
        """DI evaluate returning True must allow the stream to proceed."""
        client = _make_client(allow=True)
        resp = client.post(
            "/api/chat/stream",
            json={
                "messages": [{"role": "user", "content": "hello"}],
                "vault_id": 5,
            },
        )
        assert resp.status_code == 200
        assert "Test response" in resp.text


class TestChatNonStreamPolicyDI:
    def test_chat_denied_returns_403(self):
        """Non-stream /chat must also enforce the DI policy with a 403."""
        client = _make_client(allow=False)
        resp = client.post(
            "/api/chat",
            json={"message": "hello", "vault_id": 5},
        )
        assert resp.status_code == 403
        assert "No read access" in resp.text
