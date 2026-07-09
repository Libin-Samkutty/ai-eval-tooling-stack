"""Application configuration via environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class VertexConfig:
    """Vertex AI model configuration."""

    project_id: str = field(default_factory=lambda: os.environ["VERTEX_PROJECT_ID"])
    gemini_model: str = field(
        default_factory=lambda: os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
    )
    claude_judge_model: str = field(
        default_factory=lambda: os.environ.get("CLAUDE_JUDGE_MODEL", "claude-3-5-sonnet@20240620")
    )
    claude_haiku_model: str = field(
        default_factory=lambda: os.environ.get("CLAUDE_HAIKU_MODEL", "claude-3-haiku@20240307")
    )


@dataclass(frozen=True)
class ChromaConfig:
    """ChromaDB vector store configuration."""

    host: str = field(default_factory=lambda: os.environ.get("CHROMA_HOST", "localhost"))
    port: int = field(default_factory=lambda: int(os.environ.get("CHROMA_PORT", "8001")))
    collection: str = field(default_factory=lambda: os.environ.get("CHROMA_COLLECTION", "rag_docs"))


@dataclass(frozen=True)
class SessionConfig:
    """Session store configuration."""

    db_path: str = field(default_factory=lambda: os.environ.get("SESSION_DB_PATH", "./sessions.db"))


@dataclass(frozen=True)
class MLflowConfig:
    """MLflow tracking configuration."""

    tracking_uri: str = field(
        default_factory=lambda: os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
    )


@dataclass(frozen=True)
class AppConfig:
    """Top-level application configuration."""

    vertex: VertexConfig = field(default_factory=VertexConfig)
    chroma: ChromaConfig = field(default_factory=ChromaConfig)
    session: SessionConfig = field(default_factory=SessionConfig)
    mlflow: MLflowConfig = field(default_factory=MLflowConfig)


def load_config() -> AppConfig:
    """Load configuration from environment variables."""
    return AppConfig()
