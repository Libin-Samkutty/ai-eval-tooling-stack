"""Tests for the chatbot /query endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Health endpoint ────────────────────────────────────


@pytest.mark.asyncio
async def test_health_endpoint():
    """Health endpoint returns ok."""
    from httpx import ASGITransport, AsyncClient

    from src.chatbot.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


# ── Query request validation ──────────────────────────


@pytest.mark.asyncio
async def test_query_missing_question():
    """Query without question field returns 422."""
    from httpx import ASGITransport, AsyncClient

    from src.chatbot.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/query", json={})
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_query_success(tmp_path, monkeypatch):
    """A query with a mocked generator returns a 200 with the answer and sources."""
    from httpx import ASGITransport, AsyncClient

    import src.chatbot.main as main_module
    from src.chatbot.main import app
    from src.chatbot.session import SessionStore

    # main.session_store is a module-level singleton built at first import;
    # swap it for an isolated store so this test doesn't write to whatever
    # sessions.db another test/process already initialized it with.
    monkeypatch.setattr(main_module, "session_store", SessionStore(str(tmp_path / "sessions.db")))

    transport = ASGITransport(app=app)
    with patch(
        "src.chatbot.main.retrieve_and_generate",
        new=AsyncMock(return_value=("Test answer", ["chunk1", "chunk2"])),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/query", json={"question": "What is RAG?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Test answer"
    assert body["sources"] == ["chunk1", "chunk2"]
    assert body["session_id"]


# ── LangSmith tracing ──────────────────────────────────


@pytest.mark.asyncio
async def test_query_success_closes_langsmith_trace(tmp_path, monkeypatch):
    """A successful query creates a run with start_time and closes it with end_time.

    Regression test: the old trace_query() never set end_time/called
    update_run, so every run stayed stuck "running" in the LangSmith UI.
    """
    from httpx import ASGITransport, AsyncClient

    import src.chatbot.main as main_module
    import src.chatbot.tracing as tracing_module
    from src.chatbot.main import app
    from src.chatbot.session import SessionStore

    monkeypatch.setattr(main_module, "session_store", SessionStore(str(tmp_path / "sessions.db")))
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    monkeypatch.setattr(tracing_module, "_LANGSMITH_AVAILABLE", True)

    mock_client = MagicMock()
    monkeypatch.setattr(tracing_module, "LangSmithClient", MagicMock(return_value=mock_client))

    transport = ASGITransport(app=app)
    with patch(
        "src.chatbot.main.retrieve_and_generate",
        new=AsyncMock(return_value=("Test answer", ["chunk1"])),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/query", json={"question": "What is RAG?"})

    assert response.status_code == 200
    mock_client.create_run.assert_called_once()
    assert "start_time" in mock_client.create_run.call_args.kwargs
    mock_client.update_run.assert_called_once()
    assert "end_time" in mock_client.update_run.call_args.kwargs
    assert mock_client.update_run.call_args.kwargs["error"] is None


@pytest.mark.asyncio
async def test_query_failure_still_closes_langsmith_trace(tmp_path, monkeypatch):
    """A query that raises still closes the LangSmith run, with the error recorded.

    Regression test: trace_query() used to be called only after a
    successful response was built, so failed queries produced no trace
    at all.
    """
    from httpx import ASGITransport, AsyncClient

    import src.chatbot.main as main_module
    import src.chatbot.tracing as tracing_module
    from src.chatbot.main import app
    from src.chatbot.session import SessionStore

    monkeypatch.setattr(main_module, "session_store", SessionStore(str(tmp_path / "sessions.db")))
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    monkeypatch.setattr(tracing_module, "_LANGSMITH_AVAILABLE", True)

    mock_client = MagicMock()
    monkeypatch.setattr(tracing_module, "LangSmithClient", MagicMock(return_value=mock_client))

    transport = ASGITransport(app=app)
    with patch(
        "src.chatbot.main.retrieve_and_generate",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/query", json={"question": "What is RAG?"})

    assert response.status_code == 500
    mock_client.create_run.assert_called_once()
    mock_client.update_run.assert_called_once()
    assert mock_client.update_run.call_args.kwargs["error"] == "boom"
    assert mock_client.update_run.call_args.kwargs["outputs"] is None


# ── Session store ─────────────────────────────────────


def test_session_store_add_and_get(tmp_path):
    """Session store correctly stores and retrieves turns."""
    from src.chatbot.session import SessionStore

    store = SessionStore(str(tmp_path / "test_sessions.db"))

    # Empty session
    history = store.get_history("test-session-1")
    assert history == []

    # Add turns
    store.add_turn("test-session-1", "Hello?", "Hi there!")
    store.add_turn("test-session-1", "How are you?", "I'm good!")

    history = store.get_history("test-session-1")
    assert len(history) == 2
    assert history[0].question == "Hello?"
    assert history[1].answer == "I'm good!"


def test_session_store_clear(tmp_path):
    """Session store clear removes all turns."""
    from src.chatbot.session import SessionStore

    store = SessionStore(str(tmp_path / "test_sessions.db"))
    store.add_turn("test-session-2", "Hello?", "Hi!")
    store.clear_session("test-session-2")

    history = store.get_history("test-session-2")
    assert history == []


# ── Config ─────────────────────────────────────────────


def test_config_defaults(monkeypatch):
    """Config loads with defaults when env vars are set."""
    monkeypatch.setenv("VERTEX_PROJECT_ID", "test-project")

    from src.chatbot.config import load_config

    config = load_config()
    assert config.vertex.project_id == "test-project"
    assert config.chroma.host == "localhost"
    assert config.chroma.port == 8001
