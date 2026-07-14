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

Context Recall is intentionally dropped to keep call volume manageable.

API call volume: RAGAS's real Context Precision issues one judge call per
retrieved chunk (top_k=5), Faithfulness is 2 calls (fixed), Answer Relevancy
at default strictness=3 is 3 calls — 10 judge calls + 1 /query call = 11
calls/question. EVAL_DATASET_SIZE is set to 10 for this eval specifically
(not the usual 20) to land at ~110 calls/cycle, matching this project's
documented quality-cycle budget while keeping the real LLM-judged metrics
rather than a cheaper non-LLM substitute.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import httpx
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
    1. Send the question to /query, collecting the answer and retrieved
       sources (the chatbot's own retrieval, used as `retrieved_contexts`)
    2. Evaluate with RAGAS metrics (context precision, faithfulness,
       answer relevancy), judged by Claude Haiku on Vertex AI
    """
    from langchain_google_vertexai import VertexAIEmbeddings
    from langchain_google_vertexai.model_garden import ChatAnthropicVertex
    from ragas import EvaluationDataset, evaluate
    from ragas.dataset_schema import EvaluationResult, MultiTurnSample, SingleTurnSample
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import AnswerRelevancy, ContextPrecision, Faithfulness

    from src.chatbot.config import load_config

    config = load_config()
    items = load_golden_dataset(dataset_path, limit=limit)

    samples: list[SingleTurnSample | MultiTurnSample] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for item in items:
            response = await client.post(f"{chatbot_url}/query", json={"question": item.question})
            response.raise_for_status()
            data = response.json()
            samples.append(
                SingleTurnSample(
                    user_input=item.question,
                    response=data["answer"],
                    retrieved_contexts=data["sources"],
                    reference=item.reference_answer,
                    reference_contexts=item.ground_truth_contexts,
                )
            )
            logger.info("ragas_query_collected", dataset_id=item.id)

    judge_llm = LangchainLLMWrapper(
        ChatAnthropicVertex(
            model_name=config.vertex.claude_haiku_model,
            project=config.vertex.project_id,
            location=config.vertex.claude_location,
        )
    )
    judge_embeddings = LangchainEmbeddingsWrapper(
        VertexAIEmbeddings(project=config.vertex.project_id, model="text-embedding-004")
    )

    dataset = EvaluationDataset(samples=samples)
    eval_result = evaluate(
        dataset,
        metrics=[ContextPrecision(), Faithfulness(), AnswerRelevancy()],
        llm=judge_llm,
        embeddings=judge_embeddings,
    )
    # evaluate()'s return type is a Union with Executor only when
    # return_executor=True is passed, which we never do — this is always
    # a real EvaluationResult at runtime.
    assert isinstance(eval_result, EvaluationResult)

    results = [
        RAGASResult(
            question=item.question,
            dataset_id=item.id,
            context_precision=score.get("context_precision"),
            faithfulness=score.get("faithfulness"),
            answer_relevancy=score.get("answer_relevancy"),
        )
        for item, score in zip(items, eval_result.scores, strict=True)
    ]
    for result in results:
        logger.info("ragas_item_evaluated", dataset_id=result.dataset_id)

    logger.info("ragas_eval_complete", count=len(results))
    return results


async def _main() -> None:
    from src.chatbot.config import load_config
    from src.eval.mlflow_logger import init_mlflow, log_ragas_results

    chatbot_url = os.environ.get("CHATBOT_URL", "http://localhost:8000")
    dataset_path = os.environ.get("GOLDEN_DATASET_PATH", "./data/golden_dataset.json")
    mlflow_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
    limit = int(os.environ.get("EVAL_DATASET_SIZE", "20"))

    results = await run_ragas_eval(dataset_path, chatbot_url, limit=limit)

    init_mlflow(mlflow_uri)
    log_ragas_results(
        [r.model_dump() for r in results],
        judge_model=load_config().vertex.claude_haiku_model,
    )


if __name__ == "__main__":
    asyncio.run(_main())
