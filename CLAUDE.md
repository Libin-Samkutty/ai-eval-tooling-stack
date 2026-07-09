# CLAUDE.md — AI Assistant Guidelines

> This file provides context for AI coding assistants (Claude, Cursor, Copilot,
> etc.) working on this codebase. Read it before making changes.

## Project Summary

This is a local, lightweight AI evaluation tooling stack. We build a minimal
RAG chatbot (FastAPI + Chroma + Vertex AI Gemini) and wrap it with real
open-source eval/safety libraries. The model layer (Vertex AI) is the only
paid component. Everything else is self-hosted OSS running on a single-node
`kind` Kubernetes cluster.

**Core principle: real tool integration, not reimplementing metrics.** If a
library exists for it, we use it. We do not write custom metric
implementations.

## Critical Constraints — Read Before Coding

### Version Pins (Non-Negotiable Without Discussion)

- **RAGAS**: pinned to `0.3.9`. Do NOT upgrade. Version 0.4.3 has a broken
  `langchain_community.chat_models.vertexai` import. This is tracked upstream
  (GitHub issues #2741, #2745). If a newer version fixes it, document the
  change explicitly in the commit message and README.
- **RAGAS 0.3.9 is LangChain-bound throughout** — every LLM call goes through
  a LangChain wrapper. This is known and accepted.
- Check `pyproject.toml` for all other pins before changing dependencies.

### Model Layer Rules

- **Gemini** = generator (produces answers to user queries)
- **Claude** = judge (evaluates answers, drives red-team orchestration)
- **Never use the same model for generation and judging** — this avoids
  self-grading bias.
- **High-volume calls** use `claude-3-haiku` on Vertex (verify exact model
  string). Reserve Sonnet for low-frequency, high-stakes judging only.

### Concurrency Rules

- **Never run RAGAS and DeepEval eval Jobs in parallel** — both write to
  MLflow's SQLite backend and will hit lock contention.
- **Never run quality and safety cycles concurrently** for the same reason.
- Eval Jobs are ephemeral Kubernetes `Job`/`CronJob` resources, not long-running
  Deployments.

### API Call Budget

- Quality cycle: ~90–110 calls. Safety cycle: ~50–60 calls. Both under 200.
- If you add a new eval metric or test case, calculate its call cost and
  verify it fits within the budget. Document the addition.
- RAGAS: 20 questions × ~3 calls = ~60. DeepEval: 20 questions × ~4 calls = ~80.
  They alternate — never both in the same cycle.

## Architecture Decisions to Respect

### RAG Surface is Minimal by Design

The `/query` endpoint is **not** a full chat product. It exists solely to give
every downstream eval/safety tool something real to work on. Do not add
features to the chatbot that aren't required by the eval pipeline.

### LangSmith Instrumentation is Manual

We use the LangSmith SDK for **manual** instrumentation on the FastAPI
endpoint, not LangChain auto-instrumentation. This is intentional — it
demonstrates SDK-level instrumentation on a plain Python service. Do not add
LangChain auto-trace wiring.

### Guardrails AI is In-Process

Guardrails AI runs inside the chatbot process, not as a separate microservice.
Do not extract it into its own Deployment.

### Kubernetes Topology

- **3 standing Deployments**: Chroma (with PVC), Chatbot (no PVC), MLflow (with PVC)
- **Ephemeral Jobs**: All eval/safety runs are `Job` or `CronJob` resources
- **Access**: `kubectl port-forward` only — no ingress controller
- **Cluster**: `kind` single-node

## Development Workflow

### Setup

```bash
pip install -e ".[dev]"
# Ensure kind cluster is running
kind create cluster --name eval-stack  # first time only
```

### Running Locally (without K8s)

```bash
# Start Chroma locally
docker run -p 8001:8000 chromadb/chroma

# Start MLflow locally
mlflow server --backend-store-uri sqlite:///mlflow.db --default-artifact-root ./mlartifacts

# Run the chatbot
uvicorn src.chatbot.main:app --reload --port 8000
```

### Testing

```bash
# Unit tests
pytest tests/ -v

# Type checking
mypy src/

# Linting
ruff check src/ tests/
ruff format --check src/ tests/
```

### Adding a New Eval Metric

1. Add it to the appropriate module (`src/eval/` or `src/redteam/`)
2. Calculate API call cost and verify it fits the budget
3. Add a Kubernetes Job manifest in `k8s/jobs/`
4. Log results to MLflow via `src/eval/mlflow_logger.py`
5. Update `PLAN.md` and `docs/api-call-budget.md`

### Adding a New Dependency

1. Add to `pyproject.toml` under the appropriate optional group
2. Check for version conflicts with existing pins (especially LangChain ecosystem)
3. If it's a LangChain-adjacent library, verify compatibility with RAGAS 0.3.9
4. Document any known issues in the dependency's comment

## Code Style

- **Python 3.11+** — use modern syntax (type hints, `match`, `TaskGroup`, etc.)
- **Pydantic v2** for all data models and config
- **Instructor** for structured LLM output (not raw JSON parsing)
- **FastAPI** for all HTTP endpoints
- **async/await** throughout — no blocking calls in async endpoints
- **Type hints** on all public functions and classes
- **Docstrings** on public APIs; inline comments only for non-obvious logic
- **No print statements** — use `structlog` or Python `logging`
- **Error handling** — never let exceptions bubble to the user; log and return
  structured error responses

## File Naming Conventions

- Python modules: `snake_case.py`
- K8s manifests: `kebab-case.yaml`
- Docker images: `oss-ai-eval-<component>` (e.g., `oss-ai-eval-chatbot`)
- Environment variables: `UPPER_SNAKE_CASE` with project prefix where ambiguous

## Golden Dataset Schema

```json
{
  "id": "string",
  "question": "string",
  "ground_truth_contexts": ["string"],
  "reference_answer": "string",
  "metadata": { "topic": "string", "difficulty": "string" }
}
```

This schema is DVC-versioned. Any change = new DVC-tracked version. Do not
modify without updating the DVC tracking.

## Things Explicitly Out of Scope

- Argo Workflows/CD
- Prometheus/Grafana monitoring
- Ingress controller / external access
- Full chat product features (streaming, auth, multi-user)
- Self-hosted Phoenix (we use hosted LangSmith)
- Custom metric implementations (use the real libraries)
- Postgres or MinIO for MLflow (SQLite + local disk at this tier)

## When In Doubt

1. Check [PLAN.md](./PLAN.md) — it contains the rationale for every decision
2. Check [docs/known-limitations.md](./docs/known-limitations.md) before
   "fixing" something that's an accepted limitation
3. Ask before changing version pins
4. Ask before adding any component that requires a new Kubernetes Deployment
