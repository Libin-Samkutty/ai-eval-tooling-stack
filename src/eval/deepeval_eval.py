"""DeepEval evaluation — quality metrics for the RAG pipeline.

Alternates with RAGAS — never both in the same quality cycle.
Both write to MLflow SQLite backend, and concurrent writes cause
lock contention.

API call volume: with include_reason=False on all four metrics (drops the
free-text explanation only, no accuracy cost), each metric is 1-3 calls —
Answer Relevancy 2, Faithfulness 3, Contextual Precision 1, Hallucination 1
= 7 judge calls + 1 /query call = 8 calls/question. 20 questions x 8 calls
= ~160 calls per cycle — under the 200 hard cap, and DeepEval never runs
in the same cycle as RAGAS/promptfoo (see module docstring above).
"""

from __future__ import annotations

import asyncio
import os

import httpx
import structlog
from pydantic import BaseModel

from src.eval.ragas_eval import load_golden_dataset

logger = structlog.get_logger(__name__)


class DeepEvalResult(BaseModel):
    """Result from a single DeepEval evaluation run."""

    answer_relevancy: float | None = None
    faithfulness: float | None = None
    contextual_precision: float | None = None
    hallucination: float | None = None
    question: str
    dataset_id: str


async def run_deepeval_eval(
    dataset_path: str,
    chatbot_url: str,
    limit: int = 20,
) -> list[DeepEvalResult]:
    """Run DeepEval evaluation against the chatbot.

    For each item in the golden dataset:
    1. Send the question to /query, collecting the answer and retrieved
       sources
    2. Evaluate with DeepEval metrics, judged by Claude Haiku on Vertex AI
    """
    # Imported from its defining module, not `deepeval` or `deepeval.evaluate`
    # directly — deepeval re-exports the `evaluate` function under the same
    # name as the `deepeval.evaluate` submodule, which mypy resolves to the
    # (non-callable) module rather than the function.
    from deepeval.evaluate.evaluate import evaluate
    from deepeval.metrics import (
        AnswerRelevancyMetric,
        ContextualPrecisionMetric,
        FaithfulnessMetric,
        HallucinationMetric,
    )
    from deepeval.test_case import LLMTestCase

    from src.chatbot.config import load_config
    from src.eval.vertex_claude_model import VertexClaudeModel

    config = load_config()
    items = load_golden_dataset(dataset_path, limit=limit)

    judge = VertexClaudeModel(
        model_name=config.vertex.claude_haiku_model,
        project=config.vertex.project_id,
        location=config.vertex.claude_location,
    )

    test_cases: list[LLMTestCase] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for item in items:
            response = await client.post(f"{chatbot_url}/query", json={"question": item.question})
            response.raise_for_status()
            data = response.json()
            test_cases.append(
                LLMTestCase(
                    input=item.question,
                    actual_output=data["answer"],
                    expected_output=item.reference_answer,
                    retrieval_context=data["sources"],
                    context=item.ground_truth_contexts,
                )
            )
            logger.info("deepeval_query_collected", dataset_id=item.id)

    metrics = [
        AnswerRelevancyMetric(model=judge, include_reason=False),
        FaithfulnessMetric(model=judge, include_reason=False),
        ContextualPrecisionMetric(model=judge, include_reason=False),
        HallucinationMetric(model=judge, include_reason=False),
    ]
    eval_result = evaluate(test_cases, metrics)

    results: list[DeepEvalResult] = []
    for item, test_result in zip(items, eval_result.test_results, strict=True):
        scores = {m.name: m.score for m in (test_result.metrics_data or [])}
        results.append(
            DeepEvalResult(
                question=item.question,
                dataset_id=item.id,
                answer_relevancy=scores.get("Answer Relevancy"),
                faithfulness=scores.get("Faithfulness"),
                contextual_precision=scores.get("Contextual Precision"),
                hallucination=scores.get("Hallucination"),
            )
        )
        logger.info("deepeval_item_evaluated", dataset_id=item.id)

    logger.info("deepeval_eval_complete", count=len(results))
    return results


async def _main() -> None:
    from src.chatbot.config import load_config
    from src.eval.mlflow_logger import init_mlflow, log_deepeval_results

    chatbot_url = os.environ.get("CHATBOT_URL", "http://localhost:8000")
    dataset_path = os.environ.get("GOLDEN_DATASET_PATH", "./data/golden_dataset.json")
    mlflow_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
    limit = int(os.environ.get("EVAL_DATASET_SIZE", "20"))

    results = await run_deepeval_eval(dataset_path, chatbot_url, limit=limit)

    init_mlflow(mlflow_uri)
    log_deepeval_results(
        [r.model_dump() for r in results],
        judge_model=load_config().vertex.claude_haiku_model,
    )


if __name__ == "__main__":
    asyncio.run(_main())
