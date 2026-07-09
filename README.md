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
| **Orchestration** | Kubernetes (`kind`) | 3 standing Deployments, ephemeral Jobs/CronJobs |
| **CI** | GitHub Actions | Build/push images only |

## Prerequisites

- **Docker** (for building images)
- **kind** (Kubernetes in Docker — single-node local cluster)
- **kubectl** configured to talk to your `kind` cluster
- **Python 3.11+**
- **Vertex AI** service account JSON with `VERTEX_PROJECT_ID`
- **LangSmith** API key (free Developer tier)
- **DVC** installed (`pip install dvc`)

## Quick Start

```bash
# 1. Clone and install
git clone <repo-url> && cd oss-ai-eval-stack
pip install -e ".[dev]"

# 2. Create kind cluster
kind create cluster --name eval-stack
kubectl cluster-info --context kind-eval-stack

# 3. Set credentials
export VERTEX_PROJECT_ID="your-gcp-project"
export GOOGLE_APPLICATION_CREDENTIALS="./service-account.json"
export LANGSMITH_API_KEY="your-langsmith-key"
export LANGSMITH_PROJECT="oss-ai-eval-stack"

# 4. Deploy standing services
kubectl apply -f k8s/chroma-deployment.yaml
kubectl apply -f k8s/mlflow-deployment.yaml
kubectl apply -f k8s/chatbot-deployment.yaml

# 5. Seed the vector store
python scripts/seed_chroma.py

# 6. Port-forward and test
kubectl port-forward svc/chatbot 8000:8000
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is retrieval-augmented generation?"}'

# 7. Run an eval cycle
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

See [docs/known-limitations.md](./docs/known-limitations.md) for full details.

## Open Decisions

| # | Decision | Blocking |
|---|---|---|
| 1 | Re-check RAGAS for a release newer than 0.4.3 that fixes the broken import | Phase 4 |
| 2 | Verify `claude-3-haiku@20240307` model string on Vertex | Phase 1 |
| 3 | ~~Confirm LangChain-Vertex wrapper compatibility at RAGAS 0.3.9~~ — resolved: pin `langchain-community<0.4.2` (0.4.2 removed the `chat_models.vertexai` import RAGAS 0.3.9 uses) | Done |
| 4 | Lock golden dataset schema before Phase 3 completes | Phase 4 |
| 5 | Define PyRIT XPIA attack loop interface to `/query` endpoint | Phase 6 |

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for development workflow and
conventions.

## License

MIT — see [LICENSE](./LICENSE).
