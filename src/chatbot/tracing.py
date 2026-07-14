"""LangSmith SDK instrumentation — manual tracing for the /query endpoint.

We use manual SDK instrumentation rather than LangChain auto-instrumentation.
This demonstrates SDK-level tracing on a plain Python service, which is a
more transferable skill.

Limitations (documented in README):
- 14-day trace retention on free tier
- 5,000 traces/month hard cap
- Hosted service — traces leave the local cluster
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog

logger = structlog.get_logger(__name__)

_LANGSMITH_AVAILABLE = False
try:
    from langsmith import Client as LangSmithClient

    _LANGSMITH_AVAILABLE = True
except ImportError:
    logger.warning("langsmith_not_available", detail="langsmith package not installed")


def _is_tracing_enabled() -> bool:
    """Check if LangSmith tracing is enabled."""
    return (
        _LANGSMITH_AVAILABLE
        and os.environ.get("LANGSMITH_TRACING", "").lower() == "true"
        and bool(os.environ.get("LANGSMITH_API_KEY"))
    )


def start_query_trace(question: str, session_id: str) -> UUID | None:
    """Create the LangSmith run at the start of /query.

    Returns the run_id so the caller can close it later via
    `end_query_trace`, regardless of success or failure. Returns None if
    tracing is disabled or run creation fails — this is always a safe
    no-op for the caller.
    """
    if not _is_tracing_enabled():
        logger.debug("tracing_skipped", reason="tracing not enabled")
        return None

    run_id = uuid4()
    try:
        client = LangSmithClient()
        client.create_run(
            id=run_id,
            name="query",
            run_type="chain",
            inputs={"question": question, "session_id": session_id},
            start_time=datetime.now(UTC),
            project_name=os.environ.get("LANGSMITH_PROJECT", "oss-ai-eval-stack"),
        )
        logger.debug("trace_started", session_id=session_id, run_id=str(run_id))
        return run_id
    except Exception as e:
        # Tracing failures should never break the main request
        logger.warning("trace_start_failed", error=str(e))
        return None


def end_query_trace(
    run_id: UUID | None,
    condensed_question: str | None = None,
    answer: str | None = None,
    sources: list[str] | None = None,
    error: str | None = None,
) -> None:
    """Close a run started by `start_query_trace`.

    Setting `end_time` here (rather than never, as the old single-shot
    `create_run` call did) is what makes the run show as complete instead
    of stuck "running" in the LangSmith UI. Called on both the success
    path and the exception path so failed queries are traced too — no-op
    if `run_id` is None (tracing disabled or start failed).
    """
    if run_id is None or not _is_tracing_enabled():
        return

    try:
        client = LangSmithClient()
        client.update_run(
            run_id,
            end_time=datetime.now(UTC),
            outputs=(
                {
                    "condensed_question": condensed_question,
                    "answer": answer,
                    "sources": sources,
                }
                if error is None
                else None
            ),
            error=error,
        )
        logger.debug("trace_ended", run_id=str(run_id))
    except Exception as e:
        # Tracing failures should never break the main request
        logger.warning("trace_end_failed", error=str(e))
