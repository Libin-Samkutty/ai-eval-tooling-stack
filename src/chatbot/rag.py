"""RAG pipeline — Chroma retrieval + Gemini generation."""

from __future__ import annotations

from typing import cast

import chromadb
import structlog
from google.cloud import aiplatform
from langchain_google_vertexai import ChatVertexAI
from pydantic import BaseModel

from src.chatbot.config import AppConfig

logger = structlog.get_logger(__name__)

_gemini_model: ChatVertexAI | None = None


# ── Structured output schema ───────────────────────────


class GeneratedAnswer(BaseModel):
    """Structured response from the generator LLM."""

    answer: str
    confidence: float


# ── Chroma retrieval ───────────────────────────────────


def _get_chroma_client(config: AppConfig) -> chromadb.api.ClientAPI:
    """Create an HTTP client to the Chroma vector store."""
    return chromadb.HttpClient(host=config.chroma.host, port=config.chroma.port)


def retrieve(question: str, config: AppConfig, top_k: int = 5) -> list[str]:
    """Retrieve the top-k most relevant chunks from Chroma.

    Returns a list of text chunks.
    """
    client = _get_chroma_client(config)
    collection = client.get_or_create_collection(name=config.chroma.collection)

    results = collection.query(query_texts=[question], n_results=top_k)

    if results and results["documents"]:
        chunks = results["documents"][0]
        logger.info("retrieval_complete", query=question[:60], chunks_returned=len(chunks))
        return chunks

    logger.warning("retrieval_empty", query=question[:60])
    return []


# ── Gemini generation ──────────────────────────────────


async def generate(
    question: str,
    contexts: list[str],
    config: AppConfig,
) -> str:
    """Generate an answer using Gemini, grounded in retrieved contexts.

    Uses Vertex AI Gemini as the generator model. The prompt explicitly
    instructs the model to ground its answer in the provided contexts.
    """
    context_block = "\n\n---\n\n".join(contexts) if contexts else "No relevant context found."

    prompt = f"""You are a helpful assistant answering questions based on the provided context.
If the context does not contain enough information to answer the question, say so clearly.
Do not make up information beyond what is in the context.

## Context

{context_block}

## Question

{question}

## Answer"""

    model = _get_gemini_model(config)
    response = await model.ainvoke(prompt)
    answer = cast(str, response.content)

    logger.info("generation_complete", question=question[:60], answer_length=len(answer))
    return answer


def _get_gemini_model(config: AppConfig) -> ChatVertexAI:
    """Get the (module-cached) Gemini chat model via LangChain-Vertex wrapper.

    NOTE: RAGAS 0.3.9 is LangChain-bound throughout, so we use the
    LangChain wrapper here for consistency across the stack.
    """
    global _gemini_model
    if _gemini_model is None:
        aiplatform.init(project=config.vertex.project_id)
        _gemini_model = ChatVertexAI(
            model_name=config.vertex.gemini_model,
            project=config.vertex.project_id,
        )
    return _gemini_model


# ── Combined retrieve + generate ───────────────────────


async def retrieve_and_generate(
    question: str,
    config: AppConfig,
    top_k: int = 5,
) -> tuple[str, list[str]]:
    """Full RAG pipeline: retrieve contexts, then generate an answer.

    Returns:
        Tuple of (answer_text, source_chunks)
    """
    contexts = retrieve(question, config, top_k=top_k)
    answer = await generate(question, contexts, config)
    return answer, contexts
