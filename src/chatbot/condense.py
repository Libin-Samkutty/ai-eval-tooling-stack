"""Query condensation — rewrite follow-up questions into standalone queries.

When a user asks a follow-up question in a multi-turn conversation, this
module uses an LLM call to rewrite it into a standalone question using the
conversation history. This adds one LLM call per non-first turn.
"""

from __future__ import annotations

import structlog
from langchain_google_vertexai import ChatVertexAI

from src.chatbot.config import AppConfig
from src.chatbot.session import Turn

logger = structlog.get_logger(__name__)

_condense_model: ChatVertexAI | None = None

CONDENSE_PROMPT = """Given the following conversation history and a follow-up question,
rephrase the follow-up question to be a standalone question that can be understood
without the conversation context.

## Conversation History
{history}

## Follow-up Question
{question}

## Standalone Question
Return ONLY the rephrased standalone question, nothing else."""


async def condense_query(
    question: str,
    history: list[Turn],
    config: AppConfig,
) -> str:
    """Rewrite a follow-up question into a standalone question.

    Uses Gemini (same as the generator) for the condensation call.
    This adds one LLM call per non-first turn — account for this in
    API call budgets.

    Args:
        question: The current follow-up question.
        history: Previous conversation turns.
        config: Application configuration.

    Returns:
        The standalone (condensed) question.
    """
    if not history:
        return question

    # Format conversation history
    history_text = "\n".join(
        f"Human: {turn.question}\nAssistant: {turn.answer}" for turn in history
    )

    prompt = CONDENSE_PROMPT.format(history=history_text, question=question)

    model = _get_condense_model(config)
    response = await model.ainvoke(prompt)
    condensed = response.content.strip()

    logger.info(
        "query_condensed",
        original=question[:80],
        condensed=condensed[:80],
        history_turns=len(history),
    )

    return condensed


def _get_condense_model(config: AppConfig) -> ChatVertexAI:
    """Get the (module-cached) Gemini chat model used for condensation."""
    global _condense_model
    if _condense_model is None:
        _condense_model = ChatVertexAI(
            model_name=config.vertex.gemini_model,
            project=config.vertex.project_id,
            temperature=0.0,
        )
    return _condense_model
