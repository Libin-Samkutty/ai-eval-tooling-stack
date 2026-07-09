"""DeepEval evaluation — quality metrics for the RAG pipeline.

Alternates with RAGAS — never both in the same quality cycle.
Both write to MLflow SQLite backend, and concurrent writes cause
lock contention.

API call volume: 20 questions x ~4 calls/question = ~80 calls per cycle.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import structlog
from pydantic import BaseModel

from src.eval.ragas_eval import GoldenDatasetItem

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
    1. Send the question to /query
    2. Evaluate with DeepEval metrics

    TODO(phase-4): Implement actual DeepEval evaluation.
    Example structure:
        from deepeval import evaluate
        from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
        from deepeval.test_case import LLMTestCase
        from deepeval.models.llms.vertex_ai import VertexAIModel

        judge = VertexAIModel(model_name="claude-3-5-sonnet@20240620")
        test_cases = [LLMTestCase(...)]
        evaluate(test_cases, [AnswerRelevancyMetric(model=judge), ...])
    """
    data = json.loads(Path(dataset_path).read_text())
    items = [GoldenDatasetItem(**item) for item in data[:limit]]
    results: list[DeepEvalResult] = []

    for item in items:
        # TODO(phase-4): Call /query endpoint and collect response
        # TODO(phase-4): Run DeepEval metrics
        result = DeepEvalResult(
            question=item.question,
            dataset_id=item.id,
        )
        results.append(result)
        logger.info("deepeval_item_evaluated", dataset_id=item.id)

    logger.info("deepeval_eval_complete", count=len(results))
    return results


async def _main() -> None:
    from src.eval.mlflow_logger import init_mlflow, log_deepeval_results

    chatbot_url = os.environ.get("CHATBOT_URL", "http://localhost:8000")
    dataset_path = os.environ.get("GOLDEN_DATASET_PATH", "./data/golden_dataset.json")
    mlflow_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
    limit = int(os.environ.get("EVAL_DATASET_SIZE", "20"))

    results = await run_deepeval_eval(dataset_path, chatbot_url, limit=limit)

    init_mlflow(mlflow_uri)
    log_deepeval_results([r.model_dump() for r in results])


if __name__ == "__main__":
    asyncio.run(_main())
