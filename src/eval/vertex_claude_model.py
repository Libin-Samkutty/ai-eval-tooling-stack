"""Custom DeepEval LLM wrapper for Claude-on-Vertex.

DeepEval has no built-in class for Claude via Vertex AI Model Garden —
`deepeval.models.llms.anthropic_model.AnthropicModel` calls Anthropic's own
API directly (needs ANTHROPIC_API_KEY), which violates this project's rule
that Claude is invoked on Vertex. This wraps the same
`anthropic.AnthropicVertex`/`AsyncAnthropicVertex` clients that
`langchain_google_vertexai.model_garden.ChatAnthropicVertex` uses internally.
"""

from __future__ import annotations

from typing import Any

from anthropic import AnthropicVertex, AsyncAnthropicVertex
from deepeval.models.base_model import DeepEvalBaseLLM


class VertexClaudeModel(DeepEvalBaseLLM):  # type: ignore[misc]
    """DeepEval judge model backed by Claude on Vertex AI Model Garden."""

    def __init__(self, model_name: str, project: str, location: str) -> None:
        self.model_name = model_name
        self.project = project
        self.location = location
        super().__init__(model_name)

    def load_model(self, *args: Any, **kwargs: Any) -> Any:
        # Base class types this as -> "DeepEvalBaseLLM", but every real
        # implementation (e.g. deepeval's own GPTModel) returns its raw
        # client object, not a DeepEvalBaseLLM — matching that convention.
        return AnthropicVertex(project_id=self.project, region=self.location)

    def generate(self, prompt: str, schema: Any = None) -> str:
        # Build the client directly rather than via self.load_model() —
        # that method returns Any (see its comment above), which would
        # widen `message` (and this function's return type) to Any too.
        client = AnthropicVertex(project_id=self.project, region=self.location)
        message = client.messages.create(
            model=self.model_name,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text: str = next(block.text for block in message.content if block.type == "text")
        return text

    async def a_generate(self, prompt: str, schema: Any = None) -> str:
        client = AsyncAnthropicVertex(project_id=self.project, region=self.location)
        message = await client.messages.create(
            model=self.model_name,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text: str = next(block.text for block in message.content if block.type == "text")
        return text

    def get_model_name(self) -> str:
        return f"{self.model_name} (Vertex)"
