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


def trace_query(
    question: str,
    condensed_question: str | None,
    answer: str,
    sources: list[str],
    session_id: str,
) -> None:
    """Log a query trace to LangSmith.

    Uses the LangSmith SDK for manual instrumentation. This is called
    after the /query endpoint completes.

    If tracing is not configured (no API key or tracing disabled),
    this is a silent no-op.
    """
    if not _is_tracing_enabled():
        logger.debug("tracing_skipped", reason="tracing not enabled")
        return

    try:
        client = LangSmithClient()
        # Log the run manually via the SDK
        # TODO(phase-5): Implement proper LangSmith run creation with
        # inputs/outputs/metadata for full trace visibility in the UI
        client.create_run(
            name="query",
            run_type="chain",
            inputs={
                "question": question,
                "condensed_question": condensed_question,
                "session_id": session_id,
            },
            outputs={
                "answer": answer,
                "sources": sources,
            },
            project_name=os.environ.get("LANGSMITH_PROJECT", "oss-ai-eval-stack"),
        )
        logger.debug("trace_logged", session_id=session_id)
    except Exception as e:
        # Tracing failures should never break the main request
        logger.warning("trace_failed", error=str(e))
