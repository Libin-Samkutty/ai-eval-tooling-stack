"""FastAPI application — single /query endpoint for RAG."""

from __future__ import annotations

import uuid

import structlog
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.chatbot.condense import condense_query
from src.chatbot.config import load_config
from src.chatbot.guardrails import apply_guardrails
from src.chatbot.rag import retrieve_and_generate
from src.chatbot.session import SessionStore
from src.chatbot.tracing import trace_query

logger = structlog.get_logger(__name__)

app = FastAPI(
    title="OSS AI Eval Stack — Chatbot",
    description="Minimal RAG endpoint for evaluation and safety tooling.",
    version="0.1.0",
)

config = load_config()
session_store = SessionStore(config.session.db_path)


# ── Request / Response Models ──────────────────────────


class QueryRequest(BaseModel):
    """Incoming query request."""

    question: str
    session_id: str | None = None


class QueryResponse(BaseModel):
    """Query response with answer and metadata."""

    answer: str
    sources: list[str]
    session_id: str
    condensed_question: str | None = None


class ErrorResponse(BaseModel):
    """Structured error response for /query failures."""

    error: str
    session_id: str


# ── Endpoint ───────────────────────────────────────────


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest) -> QueryResponse | JSONResponse:
    """Retrieve relevant context and generate an answer.

    This is the single endpoint that all downstream eval/safety tools operate
    against. It intentionally stays minimal — no streaming, no auth, no
    multi-user features.
    """
    session_id = request.session_id or str(uuid.uuid4())

    try:
        # Retrieve conversation history for multi-turn
        history = session_store.get_history(session_id)

        # Condense follow-up questions into standalone queries
        condensed_question = None
        effective_question = request.question
        if history:
            condensed_question = await condense_query(
                question=request.question,
                history=history,
                config=config,
            )
            effective_question = condensed_question
            logger.info("query_condensed", original=request.question, condensed=condensed_question)

        # Apply input guardrails
        effective_question = apply_guardrails(effective_question, direction="input")

        # Retrieve + generate
        answer, sources = await retrieve_and_generate(
            question=effective_question,
            config=config,
        )

        # Apply output guardrails
        answer = apply_guardrails(answer, direction="output")

        # Store in session history
        session_store.add_turn(session_id, request.question, answer)

        # Trace to LangSmith
        trace_query(
            question=request.question,
            condensed_question=condensed_question,
            answer=answer,
            sources=sources,
            session_id=session_id,
        )

        logger.info(
            "query_complete",
            session_id=session_id,
            question=request.question[:80],
            sources_count=len(sources),
        )

        return QueryResponse(
            answer=answer,
            sources=sources,
            session_id=session_id,
            condensed_question=condensed_question,
        )
    except Exception as e:
        logger.error(
            "query_failed",
            session_id=session_id,
            question=request.question[:80],
            error=str(e),
        )
        return JSONResponse(
            status_code=500,
            content=ErrorResponse(
                error="Failed to process query. Please try again.",
                session_id=session_id,
            ).model_dump(),
        )


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}
