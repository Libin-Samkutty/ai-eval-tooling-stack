# Contributing

## Development Environment

```bash
# Clone and install in dev mode
git clone <repo-url> && cd oss-ai-eval-stack
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Create kind cluster (first time)
kind create cluster --name eval-stack

# Load local images into kind
kind load docker-image oss-ai-eval-chatbot:latest --name eval-stack
```

## Workflow

1. **Pick a phase** from the [build order](./README.md#phased-build-order)
2. **Create a branch**: `git checkout -b phase-N/component-name`
3. **Implement** following the project's architecture and constraints in [docs/architecture.md](./docs/architecture.md) and [docs/known-limitations.md](./docs/known-limitations.md)
4. **Test**: `pytest tests/ -v && mypy src/ && ruff check src/ tests/`
5. **Commit** with a descriptive message referencing the phase
6. **PR** with description of what was built and any decisions made

## Commit Convention

```
phase(N): brief description

Longer explanation if needed.

- Bullet points for multiple changes
- Reference open decisions if resolving one
```

Examples:
```
phase(1): add single-turn /query endpoint with Chroma retrieval
phase(4): pin RAGAS to 0.3.9, add MLflow logging wrapper
phase(6): implement PyRIT XPIA orchestrator with 2 scenarios
```

## Code Review Checklist

- [ ] No version pins changed without justification
- [ ] API call budget impact calculated if adding eval metrics
- [ ] MLflow SQLite contention considered for new Jobs
- [ ] LangSmith tracing added for new LLM call paths
- [ ] K8s manifest added/updated if infrastructure changed
- [ ] `docs/architecture.md` updated if adding new architectural constraints
- [ ] Tests pass: `pytest`, `mypy`, `ruff`

## Reporting Issues

When reporting issues, include:
- Which phase/component is affected
- K8s Job logs (`kubectl logs job/<job-name>`)
- MLflow run details if eval-related
- LangSmith trace link if observability-related
