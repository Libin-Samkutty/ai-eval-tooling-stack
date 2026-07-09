"""RAGAS evaluation — quality metrics for the RAG pipeline.

PINNED to RAGAS 0.3.9. DO NOT upgrade without verifying the fix for the
broken langchain_community.chat_models.vertexai import in 0.4.3
(upstream issues #2741, #2745).

0.3.9 is LangChain-bound throughout — every LLM call goes through a
LangChain wrapper. This is known and accepted.

Metrics (capped at 3 per quality cycle):
- Context Precision: How relevant are the retrieved contexts?
- Faithfulness: Is the answer grounded in the retrieved contexts?
- Answer Relevancy: Does the answer address the question?

Context Recall is intentionally dropped to keep call volume at ~60/cycle.

API call volume: 20 questions x ~3 calls/question = ~60 calls per cycle.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import structlog
from pydantic import BaseModel

logger = structlog.get_logger(__name__)


class GoldenDatasetItem(BaseModel):
    """A single item from the golden dataset."""

    id: str
    question: str
    ground_truth_contexts: list[str]
    reference_answer: str
    metadata: dict[str, str] = {}


class RAGASResult(BaseModel):
    """Result from a single RAGAS evaluation run."""

    context_precision: float | None = None
    faithfulness: float | None = None
    answer_relevancy: float | None = None
    question: str
    dataset_id: str


def load_golden_dataset(path: str, limit: int = 20) -> list[GoldenDatasetItem]:
    """Load the golden dataset from a JSON file.

    Args:
        path: Path to the golden dataset JSON file.
        limit: Maximum number of items to load (default 20).

    Returns:
        List of golden dataset items.
    """
    data = json.loads(Path(path).read_text())
    items = [GoldenDatasetItem(**item) for item in data[:limit]]
    logger.info("golden_dataset_loaded", count=len(items), path=path)
    return items


async def run_ragas_eval(
    dataset_path: str,
    chatbot_url: str,
    limit: int = 20,
) -> list[RAGASResult]:
    """Run RAGAS evaluation against the chatbot.

    For each item in the golden dataset:
    1. Send the question to /query
    2. Evaluate with RAGAS metrics (context precision, faithfulness,
       answer relevancy)

    TODO(phase-4): Implement actual RAGAS evaluation call.
    Requires:
    - ragas==0.3.9 with working LangChain-Vertex wrapper
    - Vertex AI credentials for both Gemini (retrieval eval) and
      Claude (judge model for RAGAS metrics)

    Example structure:
        from ragas import evaluate
        from ragas.metrics import context_precision, faithfulness, answer_relevancy
        from ragas.llms import LangchainLLMWrapper
        from langchain_google_vertexai import ChatVertexAI

        judge_llm = LangchainLLMWrapper(ChatVertexAI(model_name="claude-3-5-sonnet@20240620"))
        dataset = EvaluationDataset(...)
        results = evaluate(dataset, metrics=[...], llm=judge_llm)
    """
    items = load_golden_dataset(dataset_path, limit=limit)
    results: list[RAGASResult] = []

    for item in items:
        # TODO(phase-4): Call /query endpoint and collect response
        # TODO(phase-4): Run RAGAS evaluate() with the response
        result = RAGASResult(
            question=item.question,
            dataset_id=item.id,
        )
        results.append(result)
        logger.info("ragas_item_evaluated", dataset_id=item.id)

    logger.info("ragas_eval_complete", count=len(results))
    return results


async def _main() -> None:
    from src.eval.mlflow_logger import init_mlflow, log_ragas_results

    chatbot_url = os.environ.get("CHATBOT_URL", "http://localhost:8000")
    dataset_path = os.environ.get("GOLDEN_DATASET_PATH", "./data/golden_dataset.json")
    mlflow_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
    limit = int(os.environ.get("EVAL_DATASET_SIZE", "20"))

    results = await run_ragas_eval(dataset_path, chatbot_url, limit=limit)

    init_mlflow(mlflow_uri)
    log_ragas_results([r.model_dump() for r in results])


if __name__ == "__main__":
    asyncio.run(_main())
