"""Guardrails AI integration — in-process input/output validation.

Guardrails AI runs inside the chatbot process (not a separate microservice).
This module provides input and output guardrails for the /query endpoint.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def apply_guardrails(text: str, direction: str = "input") -> str:
    """Apply guardrails to input or output text.

    Args:
        text: The text to validate/sanitize.
        direction: Either "input" (user question) or "output" (generated answer).

    Returns:
        The validated/sanitized text.

    TODO(phase-6): Implement actual Guardrails AI validators:
    - Input: PII detection, prompt injection detection, toxic language filter
    - Output: Hallucination check, PII leakage prevention, topic adherence

    For now, this is a pass-through that logs the guardrail application.
    """
    # TODO(phase-6): Replace with real Guardrails AI integration
    # Example structure:
    #
    # from guardrails import Guard
    # from guardrails.hub import ToxicLanguage, RestrictToTopic
    #
    # if direction == "input":
    #     guard = Guard().use(ToxicLanguage(...))
    # else:
    #     guard = Guard().use(RestrictToTopic(...))
    #
    # result = guard.validate(text)
    # return result.validated_output

    logger.debug("guardrails_applied", direction=direction, text_length=len(text))
    return text
