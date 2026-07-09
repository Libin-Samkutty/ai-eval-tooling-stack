# Architecture

## System Overview

```
                    ┌──────────────────────────────────────────────┐
                    │              Vertex AI (Paid)                 │
                    │  ┌─────────────┐      ┌──────────────────┐   │
                    │  │   Gemini    │      │     Claude        │   │
                    │  │ (Generator) │      │ (Judge/Red-team)  │   │
                    │  └──────┬──────┘      └────────┬─────────┘   │
                    └─────────┼──────────────────────┼─────────────┘
                              │                      │
              ┌───────────────┼──────────────────────┼───────────────┐
              │               ▼                      ▼               │
              │  ┌────────────────────┐   ┌──────────────────────┐   │
              │  │     Chatbot        │   │   Eval / Safety      │   │
              │  │   (FastAPI)        │   │   Jobs (ephemeral)   │   │
              │  │                    │   │                      │   │
              │  │  ┌──────────────┐  │   │  ┌──── RAGAS ────┐  │   │
              │  │  │ /query       │  │   │  │ DeepEval      │  │   │
              │  │  │  ├─ retrieve │  │   │  │ promptfoo     │  │   │
              │  │  │  ├─ condense │  │   │  │ PyRIT XPIA   │  │   │
              │  │  │  ├─ generate │  │   │  │ Garak         │  │   │
              │  │  │  └─ guard    │  │   │  │ Fairlearn     │  │   │
              │  │  └──────────────┘  │   │  └───────────────┘  │   │
              │  └──┬─────────┬───────┘   └──┬─────────┬────────┘   │
              │     │         │              │         │            │
              │  ┌──▼──┐  ┌───▼───┐    ┌─────▼──┐  ┌──▼──────┐     │
              │  │Chroma│  │SQLite │    │ MLflow │  │LangSmith│     │
              │  │(PVC) │  │Session│    │ (PVC)  │  │(hosted) │     │
              │  └──────┘  └───────┘    └────────┘  └─────────┘     │
              │                                                      │
              │              Kubernetes (kind)                        │
              └──────────────────────────────────────────────────────┘
```

## Component Details

### Standing Deployments (3)

| Component | Image | PVC | Purpose |
|---|---|---|---|
| **Chroma** | `chromadb/chroma` | 1Gi | Vector store for RAG retrieval |
| **Chatbot** | `oss-ai-eval-chatbot` | None | FastAPI `/query` endpoint |
| **MLflow** | `python:3.11-slim` + mlflow | 2Gi | Experiment tracking (SQLite + artifacts) |

### Ephemeral Jobs

All eval and safety runs are `Job` or `CronJob` resources — they start, run,
and terminate. This keeps the cluster lean.

**Quality cycle** (daily via CronJob):
- RAGAS sweep (alternates with DeepEval) — ~60 calls
- DeepEval sweep (alternates with RAGAS) — ~80 calls
- promptfoo regression sweep — ~30 calls

**Safety cycle** (weekly via CronJob):
- PyRIT XPIA (2 scenarios, 5-turn cap) — ~20-30 calls
- Garak probes (10 probes) — ~10 calls
- Fairlearn audit (20 items) — ~20 calls

### Data Flow

```
User Query → /query endpoint
                │
                ├─ Session Store (SQLite) → get history
                │
                ├─ Query Condensation (if multi-turn)
                │   └─ Gemini call → standalone question
                │
                ├─ Input Guardrails (Guardrails AI)
                │
                ├─ Chroma Retrieval → top-k chunks
                │
                ├─ Gemini Generation → answer grounded in context
                │
                ├─ Output Guardrails (Guardrails AI)
                │
                ├─ Session Store → save turn
                │
                └─ LangSmith Trace → log to hosted UI
```

### External Services

| Service | Type | Access | Purpose |
|---|---|---|---|
| Vertex AI | Cloud API | Service account | LLM inference |
| LangSmith | Hosted SaaS | API key | Observability/tracing |

### Key Design Decisions

1. **Separate generator and judge**: Gemini generates, Claude judges. Prevents
   self-grading bias.

2. **Minimal RAG surface**: The `/query` endpoint exists only to give eval
   tools something real to work on. Not a full chat product.

3. **Manual LangSmith instrumentation**: Demonstrates SDK-level tracing on
   plain Python, more transferable than LangChain auto-trace.

4. **SQLite MLflow backend**: Appropriate for single-user, single-node.
   Requires serialized Job execution to avoid lock contention.

5. **Guardrails in-process**: No separate microservice needed at this tier.

6. **kind cluster**: Single-node local cluster. No ingress, no load balancer,
   no multi-node complexity.
