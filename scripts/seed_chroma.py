#!/usr/bin/env python3
"""Seed Chroma with sample documents for RAG evaluation.

This script loads documents and adds them to the Chroma vector store.
Run after deploying Chroma and before running eval cycles.
"""

from __future__ import annotations

import os

import chromadb
import structlog

logger = structlog.get_logger(__name__)

# Sample documents to seed the knowledge base
SAMPLE_DOCUMENTS = [
    {
        "id": "doc_001",
        "text": (
            "Retrieval-Augmented Generation (RAG) is a technique that combines "
            "information retrieval with text generation. It first retrieves relevant "
            "documents from a knowledge base, then uses a large language model to "
            "generate an answer grounded in those retrieved contexts."
        ),
        "metadata": {"source": "rag_guide", "topic": "rag_basics"},
    },
    {
        "id": "doc_002",
        "text": (
            "Vector embeddings are dense numerical representations of text that "
            "capture semantic meaning. Text is converted into high-dimensional vectors "
            "where similar concepts are close together in the vector space. Vector "
            "similarity search computes cosine similarity between query and document "
            "vectors."
        ),
        "metadata": {"source": "embeddings_guide", "topic": "embeddings"},
    },
    {
        "id": "doc_003",
        "text": (
            "ChromaDB is an open-source vector database that stores embeddings "
            "alongside their source documents and metadata. It supports both in-memory "
            "and persistent storage modes and uses HNSW indexing for efficient "
            "approximate nearest neighbor search."
        ),
        "metadata": {"source": "chromadb_docs", "topic": "vector_store"},
    },
    {
        "id": "doc_004",
        "text": (
            "RAG evaluation metrics include faithfulness (whether the answer is "
            "grounded in retrieved context), answer relevancy (whether the answer "
            "addresses the question), context precision (whether retrieved context "
            "is relevant), and context recall (whether all relevant context was "
            "retrieved). The RAGAS framework automates this evaluation."
        ),
        "metadata": {"source": "eval_guide", "topic": "evaluation"},
    },
    {
        "id": "doc_005",
        "text": (
            "MLflow is an open-source platform for managing the ML lifecycle. "
            "Its Tracking component records parameters, metrics, and artifacts for "
            "experiment reproducibility. It supports multiple backend stores including "
            "SQLite and PostgreSQL."
        ),
        "metadata": {"source": "mlflow_docs", "topic": "tracking"},
    },
    {
        "id": "doc_006",
        "text": (
            "Prompt injection is an attack where crafted input overrides or manipulates "
            "an LLM's original instructions. Direct injection targets the system prompt, "
            "while indirect injection (XPIA) plants malicious instructions in retrieved "
            "context from a knowledge base."
        ),
        "metadata": {"source": "security_guide", "topic": "security"},
    },
    {
        "id": "doc_007",
        "text": (
            "LangSmith is a hosted platform for LLM observability, providing trace "
            "logging, evaluation, and debugging tools. The free Developer tier offers "
            "5,000 traces per month with 14-day retention. The SDK allows manual "
            "instrumentation of LLM calls."
        ),
        "metadata": {"source": "langsmith_docs", "topic": "observability"},
    },
    {
        "id": "doc_008",
        "text": (
            "AI guardrails validate and constrain LLM inputs and outputs for safety "
            "and compliance. Guardrails AI is an open-source library that provides "
            "in-process validation with support for custom validators including PII "
            "detection, topic restriction, and toxic language filtering."
        ),
        "metadata": {"source": "guardrails_docs", "topic": "safety"},
    },
    {
        "id": "doc_009",
        "text": (
            "PyRIT (Python Risk Identification Tool) is Microsoft's open-source "
            "framework for AI red-teaming. It provides orchestrators for multi-turn "
            "adversarial testing including a dedicated XPIA orchestrator for testing "
            "indirect prompt injection through knowledge base poisoning."
        ),
        "metadata": {"source": "pyrit_docs", "topic": "security"},
    },
    {
        "id": "doc_010",
        "text": (
            "DVC (Data Version Control) is an open-source tool for versioning large "
            "data files and ML models alongside code. It uses a Git-like workflow with "
            ".dvc pointer files committed to Git, while actual data is stored in a "
            "configured remote storage backend."
        ),
        "metadata": {"source": "dvc_docs", "topic": "tracking"},
    },
]


def seed_chroma() -> None:
    """Seed the Chroma vector store with sample documents."""
    host = os.environ.get("CHROMA_HOST", "localhost")
    port = int(os.environ.get("CHROMA_PORT", "8001"))
    collection_name = os.environ.get("CHROMA_COLLECTION", "rag_docs")

    logger.info("connecting_to_chroma", host=host, port=port)
    client = chromadb.HttpClient(host=host, port=port)

    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"description": "RAG evaluation knowledge base"},
    )

    # Add documents
    ids = [doc["id"] for doc in SAMPLE_DOCUMENTS]
    documents = [doc["text"] for doc in SAMPLE_DOCUMENTS]
    metadatas = [doc["metadata"] for doc in SAMPLE_DOCUMENTS]

    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    count = collection.count()
    logger.info("chroma_seeded", collection=collection_name, total_documents=count)
    print(f"Seeded {len(SAMPLE_DOCUMENTS)} documents into '{collection_name}' ({count} total)")


if __name__ == "__main__":
    seed_chroma()
