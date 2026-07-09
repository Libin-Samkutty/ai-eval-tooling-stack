# OSS AI Eval Tooling Stack

A local, lightweight project demonstrating the standard free/open-source AI
evaluation and safety tooling ecosystem. The goal is **real tool integration**
— using actual eval/safety libraries — not reimplementing metrics from scratch.

## Overview

This project builds a minimal RAG chatbot and wraps it with a comprehensive
evaluation, safety, and observability stack. Every component is a real,
industry-standard open-source library. The only paid component is the model
layer (Vertex AI: Gemini + Claude).

### Architecture at a Glance

```
┌─────────────────────────────────────────────────────────┐
│                    Vertex AI (Paid)                       │
│   Gemini (generator)  ·  Claude (judge / red-team)       │
└──────────────┬──────────────────────┬────────────────────┘
               │                      │
     ┌─────────▼─────────┐  ┌────────▼──────────┐
     │   Chatbot (FastAPI)│  │  Eval / Safety    │
     │   /query endpoint  │  │  Jobs (ephemeral) │
     └──┬──────────┬──────┘  └──┬──────────┬─────┘
        │          │             │          │
   ┌────▼──┐  ┌───▼────┐  ┌────▼───┐ ┌────▼────┐
   │Chroma │  │SQLite  │  │ MLflow │ │LangSmith│
   │(PVC)  │  │Sessions│  │ (PVC)  │ │(hosted) │
   └───────┘  └────────┘  └────────┘ └─────────┘
```

## Stack

| Layer | Tool | Notes |
|---|---|---|
| **Model** | Vertex AI (Gemini + Claude) | Separate generator/judge to avoid self-grading bias |
| **Vector Store** | ChromaDB | `Deployment` + PVC on `kind` |
| **RAG** | FastAPI `/query` | Retrieve + generate; multi-turn via SQLite + query condensation |
| **Structured Output** | Pydantic + Instructor | |
| **Experiment Tracking** | MLflow | SQLite backend, local-disk artifacts |
| **Data Versioning** | DVC | Local remote; versions golden dataset + Chroma snapshots |
| **Quality Eval** | RAGAS (pinned 0.3.9), DeepEval, promptfoo | Alternating cycles, never concurrent |
| **Observability** | LangSmith (free tier) | Manual SDK instrumentation, no LangChain auto-trace |
| **Guardrails** | Guardrails AI | In-process, not a separate microservice |
| **Red-Teaming** | PyRIT (XPIA), Garak (direct injection) | Both cover different attack surfaces |
| **Fairness** | Fairlearn | Batch job, documented limitations for text generation |
| **Stats** | scipy / statsmodels | Confidence intervals across MLflow-logged runs |
| **Orchestration** | Kubernetes (`kind`) | 3 standing Deployments, ephemeral Jobs/CronJobs; runs locally or in a [GitHub Codespace](#prerequisites) |
| **CI** | GitHub Actions | Build/push images only |

### Two Docker Images, Not One

The chatbot Deployment and the eval/redteam Jobs use **different** images —
sharing one bloats the always-on serving image with dependencies it never
uses at runtime:

- `Dockerfile.chatbot` → `oss-ai-eval-chatbot:latest` — base deps only. What
  actually serves `/query`.
- `Dockerfile.eval` → `oss-ai-eval-jobs:latest` — the `.[all]` extras
  (ragas, deepeval, pyrit, garak, fairlearn) + promptfoo. These pull in
  torch/transformers/CUDA wheels and easily exceed 5GB; the six manifests in
  `k8s/jobs/` all reference this image.
- `Dockerfile.mlflow` → `oss-ai-eval-mlflow:latest` — prebuilt so the MLflow
  container doesn't `pip install` on every restart (slow, and pip's resolver
  overhead on an unpinned version range was itself a source of OOMs).

## Prerequisites

- **Docker** (for building images)
- **kind** (Kubernetes in Docker — single-node local cluster)
- **kubectl** configured to talk to your `kind` cluster
- **Python 3.12** (all environments — local venv, CI, Codespaces — actually run
  3.12; `>=3.11` in `pyproject.toml` is a floor, not the tested version)
- **Vertex AI** service account JSON with `VERTEX_PROJECT_ID`
- **LangSmith** API key (free Developer tier)
- **DVC** installed (`pip install dvc`)

> **Resource note:** the full stack (kube-system + Chroma + MLflow + chatbot)
> needs roughly 3–4GB of headroom in whatever Docker is running in. On a
> machine with ~8GB total RAM, Docker Desktop's default VM allocation
> (typically ~3.8GB) is *not* enough once you add host OS + editor overhead —
> it will OOM-crash. If your laptop is memory-constrained, prefer a
> [GitHub Codespace](https://github.com/features/codespaces) instead of local
> Docker Desktop: `gh codespace create --machine standardLinux32gb` (4
> core/16GB, free-tier eligible) gives comfortable headroom and keeps your
> local machine untouched.

## Quick Start

These steps work identically locally or inside a Codespace — just run them
wherever your Docker/kind live.

```bash
# 1. Clone and install
git clone <repo-url> && cd ai-eval-tooling-stack
pip install -e ".[dev]"

# 2. Create kind cluster
kind create cluster --name eval-stack
kubectl cluster-info --context kind-eval-stack

# 3. Set credentials (or copy a filled-in .env — see .env.example)
export VERTEX_PROJECT_ID="your-gcp-project"
export GOOGLE_APPLICATION_CREDENTIALS="./service-account.json"
export LANGSMITH_API_KEY="your-langsmith-key"

# 4. Create the Secrets the manifests reference (not created automatically)
kubectl create secret generic vertex-credentials \
  --from-literal=project-id="$VERTEX_PROJECT_ID" \
  --from-file=service-account.json="$GOOGLE_APPLICATION_CREDENTIALS"
kubectl create secret generic langsmith-credentials \
  --from-literal=api-key="$LANGSMITH_API_KEY"

# 5. Build and load images into kind
#    chatbot: lean serving image (base deps only)
#    jobs:    heavy eval/redteam image (ragas, deepeval, pyrit, garak,
#             fairlearn, promptfoo — pulls in torch/CUDA, ~5GB+)
#    mlflow:  prebuilt (avoids a slow/flaky pip-install-at-container-start)
make build-chatbot build-eval build-mlflow
make load-images

# 6. Deploy standing services — one at a time, waiting for each to be Ready
#    (deploying all three simultaneously can spike memory past what a
#    resource-constrained Docker VM has available)
kubectl apply -f k8s/chroma-deployment.yaml
kubectl rollout status deployment/chroma --timeout=90s
kubectl apply -f k8s/mlflow-deployment.yaml
kubectl rollout status deployment/mlflow --timeout=90s
kubectl apply -f k8s/chatbot-deployment.yaml
kubectl rollout status deployment/chatbot --timeout=90s

# 7. Seed the vector store (port-forward Chroma first)
kubectl port-forward svc/chroma 8001:8001 &
python scripts/seed_chroma.py

# 8. Port-forward the chatbot and test
kubectl port-forward svc/chatbot 8000:8000 &
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is retrieval-augmented generation?"}'

# 9. Run an eval cycle
kubectl apply -f k8s/jobs/ragas-sweep.yaml
```

## Project Structure

```
.
├── src/
│   ├── chatbot/          # FastAPI RAG service
│   │   ├── main.py       # /query endpoint
│   │   ├── rag.py        # Chroma retrieval + Gemini generation
│   │   ├── session.py    # SQLite multi-turn session store
│   │   ├── condense.py   # Query condensation (follow-up → standalone)
│   │   ├── guardrails.py # Guardrails AI integration
│   │   ├── config.py     # Settings / env vars
│   │   └── tracing.py    # LangSmith SDK instrumentation
│   ├── eval/             # Quality evaluation
│   │   ├── ragas_eval.py
│   │   ├── deepeval_eval.py
│   │   ├── mlflow_logger.py  # promptfoo → MLflow glue
│   │   └── stats.py          # scipy/statsmodels analysis
│   └── redteam/          # Safety evaluation
│       ├── pyrit_xpia.py
│       ├── garak_probe.py
│       └── fairlearn_audit.py
├── k8s/                  # Kubernetes manifests
│   ├── chroma-deployment.yaml
│   ├── chatbot-deployment.yaml
│   ├── mlflow-deployment.yaml
│   ├── jobs/             # Ephemeral eval Jobs
│   └── cronjobs/         # Scheduled eval CronJobs
├── promptfoo/            # promptfoo regression test configs
├── data/                 # Golden dataset (DVC-tracked)
├── tests/                # Unit/integration tests
├── scripts/              # Utility scripts
├── docs/                 # Extended documentation
├── Dockerfile.chatbot    # Lean serving image (base deps only)
├── Dockerfile.eval       # Heavy eval/redteam Jobs image (.[all] + promptfoo)
├── Dockerfile.mlflow     # Prebuilt MLflow image
└── .github/workflows/    # CI pipelines
```

## Phased Build Order

| Phase | Scope |
|---|---|
| **1** | Core RAG — Vertex Gemini + Claude, Chroma, single-turn `/query` |
| **2** | Multi-turn — SQLite sessions + query-condensation step |
| **3** | Tracking — MLflow + DVC; finalize golden dataset schema |
| **4** | Eval — RAGAS (pinned) + DeepEval + promptfoo CronJob + MLflow glue |
| **5** | Observability — LangSmith SDK instrumentation on `/query` |
| **6** | Safety — Guardrails AI, PyRIT (+ XPIA Job), Garak, Fairlearn |
| **7** | CI — GitHub Actions |

See [PLAN.md](./PLAN.md) for full implementation details and rationale.

## API Call Budget

Eval is split into two cycles on different cadences. Neither exceeds 200 calls.

**Quality cycle** (daily / every commit): ~90–110 calls
**Safety cycle** (weekly / on-demand): ~50–60 calls

See [docs/api-call-budget.md](./docs/api-call-budget.md) for the full breakdown.

## Known Limitations

- **MLflow SQLite write contention** — Concurrent eval Jobs will hit lock
  contention. Serialize Job scheduling or run quality/safety cycles separately.
- **RAGAS pinned to 0.3.9** — Version 0.4.3 has a broken `langchain_community`
  import. This is not an oversight; it's tracked upstream (GitHub issues #2741,
  #2745). Re-verify before upgrading.
- **DVC + Chroma snapshots** — Chroma's on-disk format (SQLite + parquet
  segments) is not meaningfully diffable. DVC provides blunt-force snapshot
  versioning only.
- **LangSmith free tier** — 14-day trace retention, 5,000 traces/month cap.
  Traces leave the local cluster (hosted service).
- **Fairlearn for text** — Fairlearn is built for tabular classifiers, not
  text generation. We frame `historical_balance`-style output as the audited
  signal and document the mismatch.
- **No ingress** — Access via `kubectl port-forward` only (single local user).
- **No Argo/Prometheus** — Dropped at this tier; overhead doesn't pay off.
- **Kubernetes auto-injects Docker-links-style env vars per Service name** —
  e.g. a Service named `chroma` makes every pod in the namespace see
  `CHROMA_PORT=tcp://<clusterIP>:8001`. This collided with Chroma's own
  `CHROMA_PORT` config key and crashed it outright. Fixed via
  `enableServiceLinks: false` on all three Deployments; keep that in mind
  before naming a future Service after an env var an app already reads.
- **MLflow's built-in job scheduler must stay disabled** — MLflow 3.x's
  online-scoring/trace-archival scheduler activates ~40s after server
  startup and will OOM a single-replica local server regardless of memory
  limit (we don't use online scoring or trace archival). Set via
  `MLFLOW_SERVER_ENABLE_JOB_EXECUTION=false` in `k8s/mlflow-deployment.yaml`
  — don't remove it without re-verifying.
- **Vertex AI model availability drifts** — `gemini-1.5-flash` (the original
  default) and every `gemini-2.0-*` variant have been removed from this
  project's model catalog as of 2026-07. Currently confirmed available:
  `gemini-2.5-flash`, `gemini-2.5-pro`. Re-verify `GEMINI_MODEL` if `/query`
  starts 404ing with "Publisher model ... was not found".

See [docs/known-limitations.md](./docs/known-limitations.md) for full details.

## Open Decisions

| # | Decision | Blocking |
|---|---|---|
| 1 | Re-check RAGAS for a release newer than 0.4.3 that fixes the broken import | Phase 4 |
| 2 | Verify `claude-3-haiku@20240307` model string on Vertex — still unverified; `/query` never exercises the Claude judge path, only Gemini | Phase 1 |
| 3 | ~~Confirm LangChain-Vertex wrapper compatibility at RAGAS 0.3.9~~ — resolved: pin `langchain-community<0.4.2` (0.4.2 removed the `chat_models.vertexai` import RAGAS 0.3.9 uses) | Done |
| 4 | Lock golden dataset schema before Phase 3 completes | Phase 4 |
| 5 | Define PyRIT XPIA attack loop interface to `/query` endpoint | Phase 6 |
| 6 | ~~Verify `gemini-1.5-flash` still resolves on Vertex~~ — resolved 2026-07: it and every `gemini-2.0-*` variant 404; switched default to `gemini-2.5-flash` (confirmed available, see Known Limitations) | Done |

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for development workflow and
conventions.

## License

MIT — see [LICENSE](./LICENSE).
