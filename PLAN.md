# Project 2 Plan — Free/OSS AI Eval Tooling Stack

## Goal

A separate, local (not hosted), lightweight project demonstrating the standard
free/open-source AI eval/safety tooling ecosystem. The goal is real tool
integration — using the actual eval/safety libraries — not reimplementing
metrics from scratch. Model layer is the one paid exception: Vertex AI
(Gemini + Claude), everything else is self-hosted OSS.

---

## 1. Model layer

Vertex AI — **Gemini** generates answers, **Claude** judges and drives
red-team orchestration. Separate judge/generator avoids same-model self-grading
bias. Vertex credential setup: service account JSON, `VERTEX_PROJECT_ID`.

**High-volume call tier:** For promptfoo sweeps and other high-volume judging
calls, use `claude-3-haiku@20240307` on Vertex (verify model string before
implementation). Haiku-class volume on Sonnet will be expensive at sweep
scale. Reserve Sonnet for low-frequency, high-stakes judging (e.g., red-team
verdict).

---

## 2. RAG surface — minimal by design

A single `/query` endpoint (retrieve + generate), not a full chat product —
its only job is giving every downstream tool something real to work on.

- **Chroma** as the vector store (`Deployment` + small `PVC`)
- **Multi-turn chat:** `SQLite` session store + a query-condensation LLM call
  (rewrite follow-ups into standalone questions using prior turns) before
  retrieval. This adds one LLM call per non-first turn; account for it in
  call budgets.
- **Pydantic + Instructor** for structured output

---

## 3. Experiment tracking & versioning

- **MLflow** — tracking server, SQLite backend, local-disk artifacts (no
  Postgres/MinIO at this tier)
- **DVC** — local remote, versions the golden dataset + Chroma snapshots

**MLflow SQLite write contention:** Multiple processes writing to the same
SQLite MLflow backend on a PVC will hit lock contention if eval Jobs run
concurrently. Either enforce serialization in Job scheduling or document it as
a known limitation. Do not run the RAGAS/DeepEval sweep and the red-team Jobs
in parallel until this is resolved.

**DVC + Chroma snapshots:** Chroma's on-disk format (SQLite + parquet
segments) is not meaningfully diffable. DVC provides blunt-force snapshot
versioning for reproducibility purposes; `dvc diff` output on the vector store
will not be useful. Document this in the DVC config.

**Golden dataset schema (required before Phase 4):**

RAGAS and DeepEval both require question + ground-truth context + reference
answer triples at minimum. This schema must be locked before Phase 3 completes
or Phase 4 is blocked. Proposed schema:

```json
{
  "id": "string",
  "question": "string",
  "ground_truth_contexts": ["string"],
  "reference_answer": "string",
  "metadata": { "topic": "string", "difficulty": "string" }
}
```

DVC versions this file. Any change to the schema is a new DVC-tracked version.

---

## 4. Evaluation frameworks

The goal is real tool integration — using the actual eval/safety libraries,
not reimplementing metrics from scratch.

### RAGAS

Pin to `0.3.9`. Version `0.4.3`'s `ragas/llms/base.py` still imports
`langchain_community.chat_models.vertexai`, a path removed from
`langchain_community` (tracked upstream: GitHub issues #2741, #2745, still
open as of this writing). **Re-verify for a fixed release before implementing.**

**Important:** `0.3.9` is LangChain-bound throughout — every LLM call goes
through a LangChain wrapper. Pinning to `0.3.9` avoids the broken import in
`0.4.3` but does not eliminate the LangChain dependency. Verify that the
Vertex `VertexAI` LangChain wrapper works cleanly at `0.3.9` before
committing to the pin. Document this explicitly in the repo README so it does
not look like an oversight.

**API call volume:** Capped at 3 metrics per quality cycle (context precision,
faithfulness, answer relevancy — drop context recall). 20 questions per cycle
from the golden dataset. ~3 calls/question → **~60 calls per quality cycle.**
RAGAS and DeepEval alternate — never both in the same cycle.

### DeepEval

No known blocking issue, use as-is.

**API call volume:** Alternates with RAGAS — never both in the same quality
cycle. 20 questions, ~4 calls/question → **~80 calls per quality cycle.**

### promptfoo

Config-driven regression tests, runs as a scheduled `CronJob` logging to
MLflow.

**MLflow integration note:** promptfoo outputs JSON/CSV natively. Logging to
MLflow requires a custom Python wrapper that reads promptfoo's output and calls
`mlflow.log_metrics`. This is not automatic — account for it in Phase 4 scope.

**API call volume:** Each test case requires one generation call + one judge
call. 15 regression tests per sweep → **~30 calls per quality cycle.**

---

## 5. Observability / tracing

**LangSmith** (hosted, free Developer tier) — chosen here specifically to get
hands-on exposure to a tool that appears consistently in JDs, without the
cluster overhead of self-hosting Phoenix. LangSmith's free tier (1 seat, 5,000
traces/month) is a comfortable fit for this project's call budget: quality
cycle ~100 traces, safety cycle ~60, plus ad-hoc dev queries puts total
monthly usage at ~300–400 traces, well within the cap.

Integration is via the LangSmith SDK — manual instrumentation on the FastAPI
`/query` endpoint rather than LangChain auto-instrumentation. This is
intentional: demonstrating SDK-level instrumentation on a plain Python service
is a more transferable skill than relying on LangChain's auto-trace wiring.

**Limitations to document in the README:**
- 14-day trace retention on the free tier. Compare eval runs within a
  14-day window; older traces are gone. Accepted as a known constraint.
- Hard cap at 5,000 traces/month — traces stop ingesting at the cap, no
  queuing. At this project's volume, the cap will not be hit.
- Hosted service — traces leave the local cluster. Do not instrument with
  sensitive data.

**No cluster Deployment or PVC needed** — LangSmith is fully hosted, which
simplifies the cluster topology.

---

## 6. Guardrails

**Decision: use Guardrails AI.** (NeMo Guardrails is opinionated and
NVIDIA-oriented; Guardrails AI integrates more naturally with arbitrary Python
stacks and this project's structure.) In-process library inside the chatbot,
not a separate microservice at this tier.

---

## 7. Red-teaming

- **PyRIT** (primary) — built for multi-turn adversarial orchestration and has
  a dedicated **XPIA orchestrator** for indirect/knowledge-base prompt
  injection: plant a poisoned chunk in Chroma, query in a way that retrieves
  it, verify the hidden instruction doesn't hijack the response.

  **XPIA test design:** The attack loop must be a first-class test artifact
  (repeatable as a Kubernetes `Job`), not a one-off script:
  1. Plant — write a poisoned chunk to the Chroma KB via a seeding script
  2. Query — call `/query` with a prompt designed to retrieve the poisoned chunk
  3. Assert — Claude judge verifies the hidden instruction did not hijack the
     response
  4. Teardown — remove the poisoned chunk, restore baseline KB state

  PyRIT's XPIA orchestrator needs an explicit interface to the `/query`
  endpoint. Define the attack loop interface before Phase 6.

  **API call volume:** Capped at 2 XPIA scenarios, 5 turns max per scenario.
  ~10–15 Claude calls per scenario → **~20–30 calls per safety cycle.**
  Adjust turn cap after observing actual cost before expanding scenarios.

- **Garak** (secondary) — direct-prompt injection/jailbreak probes against the
  model endpoint. Covers a different attack surface than PyRIT's XPIA (direct
  vs. indirect injection), so both stay justified rather than one replacing the
  other.

  **API call volume:** ~1 call per probe. 10 probes → **~10 calls per safety cycle.**

---

## 8. Fairness audit

**Fairlearn** — batch `Job`, best-effort given the library is built for
tabular classifiers, not text generation. Frame `historical_balance`-style
output as the audited signal, document the mismatch rather than pretending
it's a clean fit.

**API call volume:** One inference call per item. 20-item audit batch →
**~20 calls per safety cycle.**

---

## 9. Statistical rigor

**scipy / statsmodels** — confidence intervals and significance testing across
MLflow-logged eval runs, not just raw pass rates. No additional API calls; runs
against logged metrics.

---

## 10. Kubernetes topology

`kind` (single-node local cluster).

**Standing `Deployment`s (3):**

| Deployment | PVC |
|---|---|
| Chroma | Yes — vector store data |
| Chatbot | No |
| MLflow | Yes — SQLite backend + artifacts |

LangSmith is hosted — no in-cluster Deployment or PVC required.

**Ephemeral `Job` / `CronJob`:**

Eval is split into two cycles with different cadences. Never run both
concurrently (MLflow SQLite write contention).

| Job | Cycle | Trigger | ~Calls |
|---|---|---|---|
| RAGAS sweep (alternates with DeepEval) | Quality | `CronJob` daily / every commit | ~60 |
| DeepEval sweep (alternates with RAGAS) | Quality | `CronJob` daily / every commit | ~80 |
| promptfoo regression sweep | Quality | `CronJob` daily / every commit | ~30 |
| PyRIT XPIA run (2 scenarios, 5-turn cap) | Safety | `CronJob` weekly / on-demand | ~20–30 |
| Garak probe run (10 probes) | Safety | `CronJob` weekly / on-demand | ~10 |
| Fairlearn audit (20 items) | Safety | `Job` on-demand | ~20 |

**Quality cycle total: ~90–110 calls. Safety cycle total: ~50–60 calls. Both under 200.**

**Access:** `kubectl port-forward` — no ingress controller needed for single
local user.

**Explicitly dropped at this tier:**
- Argo Workflows/CD — controller overhead only pays off with real DAG
  parallelism
- Prometheus/Grafana — no traffic pattern worth graphing yet

---

## 11. CI

GitHub Actions — build/push images. No cluster-side automation beyond that at
this tier.

---

## API call budget (estimated)

Eval is split into two cycles on different cadences. Neither exceeds 200 calls.

**Quality cycle** (daily / every commit):

| Component | Dataset | Calls | Notes |
|---|---|---|---|
| RAGAS *or* DeepEval (alternating) | 20 questions | ~60–80 | Never both in same cycle |
| promptfoo regression sweep | 15 tests | ~30 | 1 generate + 1 judge per test |
| **Quality cycle total** | | **~90–110** | |

**Safety cycle** (weekly / on-demand):

| Component | Scope | Calls | Notes |
|---|---|---|---|
| PyRIT XPIA | 2 scenarios, 5-turn cap | ~20–30 | Expand after observing cost |
| Garak | 10 probes | ~10 | 1 call/probe |
| Fairlearn audit | 20 items | ~20 | 1 inference/item |
| **Safety cycle total** | | **~50–60** | |

Interactive RAG traffic (dev/testing): ~2–3 calls per user query (retrieval is
free; generation + optional condensation + optional judge). Not counted in
cycle budgets.

**Scaling note:** The quality cycle budget is the more sensitive one — it grows
linearly with dataset size (RAGAS) and test count (promptfoo). If the golden
dataset grows beyond 20 questions, re-evaluate the RAGAS metric count before
expanding the question set. The safety cycle is cheaper and more stable.

---

## Phased build order

| Phase | Scope |
|---|---|
| 1 | Core RAG — Vertex Gemini + Claude, Chroma, single-turn `/query` — verify retrieval + generation work in-cluster before adding anything else |
| 2 | Multi-turn — SQLite sessions + query-condensation step |
| 3 | Tracking — MLflow + DVC; finalize golden dataset schema |
| 4 | Eval — RAGAS (pinned) + DeepEval + promptfoo `CronJob` + MLflow glue wrapper |
| 5 | Observability — LangSmith SDK instrumentation on `/query` endpoint; verify traces appear in hosted UI |
| 6 | Safety — Guardrails AI, PyRIT (+ XPIA Job), Garak, Fairlearn |
| 7 | CI — GitHub Actions |

---

## Open decisions

| # | Decision | Blocking |
|---|---|---|
| 1 | Re-check RAGAS for a release newer than `0.4.3` that fixes the `langchain_community.chat_models.vertexai` import before committing to the `0.3.9` pin | Phase 4 |
| 2 | Verify `claude-3-haiku@20240307` model string on Vertex before Phase 1 | Phase 1 |
| 3 | Confirm LangChain-Vertex wrapper compatibility at RAGAS `0.3.9` | Phase 4 |
| 4 | Lock golden dataset schema before Phase 3 completes | Phase 4 |
| 5 | Define PyRIT XPIA attack loop interface to `/query` endpoint | Phase 6 |
