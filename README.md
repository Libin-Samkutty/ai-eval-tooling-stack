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

### Five Docker Images, Not One

The chatbot Deployment, the eval/redteam Jobs, and the CronJob orchestrator
use **different** images — sharing one bloats the always-on serving image
with dependencies it never uses at runtime. The eval Jobs image and the
promptfoo Job image are themselves split, too (see below):

- `Dockerfile.chatbot` → `oss-ai-eval-chatbot:latest` — base deps only. What
  actually serves `/query`.
- `Dockerfile.eval` → `oss-ai-eval-jobs:latest` — the `.[all]` extras
  (ragas, deepeval, pyrit, garak, fairlearn). These pull in
  torch/transformers/CUDA wheels and easily exceed 5GB; the five
  `ragas`/`deepeval`/`pyrit`/`garak`/`fairlearn` manifests in `k8s/jobs/`
  reference this image.
- `Dockerfile.promptfoo` → `oss-ai-eval-promptfoo:latest` — base deps
  (just enough for `src/eval/mlflow_logger.py`: `mlflow` + `structlog`) plus
  npm/promptfoo. Split out of `Dockerfile.eval` because building both in one
  image needs their combined disk footprint available simultaneously during
  `docker build`'s final export step, which was tipping a 32GB Codespace
  disk over the edge — see
  [docs/known-limitations.md](./docs/known-limitations.md#codespace-disk-space-exhaustion-during-make-build-eval).
  Only `k8s/jobs/promptfoo-sweep.yaml` references this image.
- `Dockerfile.mlflow` → `oss-ai-eval-mlflow:latest` — prebuilt so the MLflow
  container doesn't `pip install` on every restart (slow, and pip's resolver
  overhead on an unpinned version range was itself a source of OOMs).
- `Dockerfile.orchestrator` → `oss-ai-eval-orchestrator:latest` — a minimal
  `python:3.11-slim` + pinned `kubectl` binary + `structlog` only (no eval
  deps at all). Backs `k8s/cronjobs/{quality,safety}-cycle.yaml`, which now
  run `scripts/run_{quality,safety}_cycle.py` as thin `kubectl`-based
  orchestrators that delete-then-create the real `k8s/jobs/*.yaml` Jobs and
  block until each completes, authorized via the narrowly-scoped
  `k8s/rbac/eval-orchestrator-rbac.yaml` ServiceAccount/Role/RoleBinding
  (`create/get/list/watch/delete` on `batch/jobs` only). See
  [docs/known-limitations.md](./docs/known-limitations.md#the-cronjob-automation-path-was-entirely-dead-fixed).

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

# 4. Create the Secrets AND ConfigMaps the manifests reference (none of
#    this is created automatically). Skipping the ConfigMaps doesn't fail
#    fast — the ragas/promptfoo Jobs' pods sit in ContainerCreating forever
#    (`kubectl describe pod` shows `FailedMount ... configmap "X" not
#    found`), and `kubectl wait` (what `make eval-quality-wait` uses) will
#    happily burn its full 45m timeout waiting on a Job that was never
#    going to finish — verified: caught this after 22 minutes of silent
#    ContainerCreating.
kubectl create secret generic vertex-credentials \
  --from-literal=project-id="$VERTEX_PROJECT_ID" \
  --from-file=service-account.json="$GOOGLE_APPLICATION_CREDENTIALS"
kubectl create secret generic langsmith-credentials \
  --from-literal=api-key="$LANGSMITH_API_KEY"
kubectl create configmap golden-dataset --from-file=data/golden_dataset.json
kubectl create configmap promptfoo-config --from-file=promptfoo/promptfooconfig.yaml

# 5. Build and load images into kind
#    chatbot:      lean serving image (base deps only)
#    jobs:         eval/redteam image (ragas, deepeval, pyrit, garak, fairlearn
#                  — pulls in torch/CUDA, ~5GB+; needs the `git` binary, since
#                  ragas 0.3.9 imports GitPython unconditionally at package
#                  init)
#    promptfoo:    separate, much lighter image (base deps + npm/promptfoo) —
#                  split out of `jobs` specifically to fix a Codespace disk
#                  problem, see note below
#    mlflow:       prebuilt (avoids a slow/flaky pip-install-at-container-start)
#    orchestrator: minimal kubectl-only image backing the CronJob orchestrator
#                  scripts (no eval deps)
make build-chatbot build-eval build-promptfoo build-mlflow build-orchestrator
make load-images
```

> **Disk space on Codespaces**: the default Codespace disk is 32GB, and
> building the full eval stack in one image (torch + `nvidia-cu13-*` CUDA
> wheels + promptfoo's npm/onnxruntime deps, ~7GB+ combined) reliably
> exhausted it — verified failure: `OSError: [Errno 28] No space left on
> device` / `failed to extract layer ...: no space left on device`, four
> times in a row, each on a different file, at 26–32GB/32GB used. What was
> tried, in order:
> - `docker builder prune -af && docker image prune -af` (host-level copies
>   of already-`kind load`ed images are redundant) — reclaimed some space,
>   **not enough alone**.
> - Deleting unused preinstalled SDKs (`/usr/share/dotnet`, `sdkman`, `go`,
>   `rvm`, `php`) — **did nothing**; they're part of the read-only base
>   image layer and don't free real disk when removed.
> - `kind delete cluster --name eval-stack` before building (the cluster's
>   containerd storage volume alone holds ~6.5GB) — helped, still not
>   enough for the combined image.
> - Stripping promptfoo's GPU-only `onnxruntime-node` binaries (never used
>   on this CPU-only cluster) — real savings, still not enough.
> - **What actually fixed it**: splitting `Dockerfile.eval` into two images
>   (`Dockerfile.eval` for the Python ML stack, `Dockerfile.promptfoo` for
>   npm/promptfoo) so no single `docker build` ever needs both footprints
>   in memory/disk at once.
>
> Also: if a build ever prints `ERROR: failed to build` / `failed to
> extract layer` partway through, don't `docker run` the resulting image to
> check whether it's usable anyway — that retries the broken unpack and can
> balloon disk further (observed: one image's reported size grew from
> 5.22GB to 16.9GB over two `docker run` invocations, and free disk hit 0).
> Just `docker rmi -f` it and rebuild clean.
>
> Full details in
> [docs/known-limitations.md](./docs/known-limitations.md#codespace-disk-space-exhaustion-during-make-build-eval).

```bash
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

# 9. Run an eval cycle (on-demand only — see Codespaces note below)
make eval-quality

# 10. (Optional) exercise the CronJob orchestrator scripts directly —
#     this is what k8s/cronjobs/*.yaml actually run in a persistent-cluster
#     deployment; verified safe to re-run (delete-before-create, not apply)
kubectl apply -f k8s/rbac/eval-orchestrator-rbac.yaml
python scripts/run_quality_cycle.py
python scripts/run_safety_cycle.py
```

> **Codespaces**: never `kubectl apply -f k8s/cronjobs/...` — a Codespace
> bills for wall-clock time regardless of internal activity and auto-stops
> based on client connections, not CPU usage, so a schedule left running here
> either silently never fires or burns the free 120 core-hours/month keeping
> a connection open to force it to. Trigger cycles on demand instead:
> `make eval-quality-wait` / `make eval-safety-wait` inside the Codespace, or
> `python scripts/run_cycle_and_stop.py quality` from your local machine,
> which also stops the Codespace the moment the cycle finishes. Details in
> [docs/known-limitations.md](./docs/known-limitations.md#cronjobs-are-incompatible-with-codespaces).

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
│   ├── redteam/          # Safety evaluation
│   │   ├── pyrit_xpia.py
│   │   ├── garak_probe.py
│   │   └── fairlearn_audit.py
│   └── orchestration/    # CronJob orchestrator (kubectl-based Job runner)
│       └── k8s_jobs.py
├── k8s/                  # Kubernetes manifests
│   ├── chroma-deployment.yaml
│   ├── chatbot-deployment.yaml
│   ├── mlflow-deployment.yaml
│   ├── jobs/             # Ephemeral eval Jobs
│   ├── cronjobs/         # Scheduled eval CronJobs (reference only — never
│   │                     # `kubectl apply`d inside a Codespace)
│   └── rbac/             # ServiceAccount/Role/RoleBinding for the orchestrator
├── promptfoo/            # promptfoo regression test configs
├── data/                 # Golden dataset (DVC-tracked)
├── tests/                # Unit/integration tests
├── scripts/              # Utility scripts (incl. run_quality_cycle.py,
│                         # run_safety_cycle.py — the orchestrator entrypoints)
├── docs/                 # Extended documentation
├── Dockerfile.chatbot      # Lean serving image (base deps only)
├── Dockerfile.eval         # Heavy eval/redteam Jobs image (.[all])
├── Dockerfile.promptfoo    # Lighter promptfoo Job image (base deps + npm)
├── Dockerfile.mlflow       # Prebuilt MLflow image
├── Dockerfile.orchestrator # Minimal kubectl-only CronJob orchestrator image
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

**Quality cycle** (daily / every commit): ~140 calls (RAGAS) or ~190 calls (DeepEval) — never both in the same cycle
**Safety cycle** (weekly / on-demand): ≤50 calls (typ. ~40–44)

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
- **Codespace disk fills up building the eval image** — the combined
  torch/CUDA + promptfoo/onnxruntime footprint (~7GB+) exceeded the default
  32GB Codespace disk four separate times. Pruning docker cache/images,
  deleting the `kind` cluster first, and stripping promptfoo's GPU-only
  onnxruntime binaries all helped but weren't sufficient alone. The actual
  fix: split `Dockerfile.eval` into it and a new, much lighter
  `Dockerfile.promptfoo`, so no single build needs both footprints at once.
  Removing unused preinstalled SDKs did nothing at all — they're part of
  the base image's read-only layer.
- **`Dockerfile.eval` was missing `git`** — ragas 0.3.9 imports GitPython
  unconditionally at package init, so `import ragas` crashed in every eval
  Job until `git` was added to the image's `apt-get install` line. Fixed.
- **Don't `docker run` an image from a failed build** — if `docker build`
  reports `failed to extract layer` partway through (usually a disk-space
  symptom) but still tags an image, running it retries the broken unpack
  and can balloon disk further instead of just failing cleanly. `docker rmi
  -f` it and rebuild instead of probing it.
- **The eval Job manifests need ConfigMaps nobody creates** — `golden-dataset`
  and `promptfoo-config` (referenced by `ragas-sweep.yaml`/`deepeval-sweep.yaml`
  and `promptfoo-sweep.yaml`) have no `kubectl create configmap` step
  anywhere in the repo. Skip it and the Job's pod sits in `ContainerCreating`
  forever (`FailedMount ... configmap "X" not found`) — `kubectl wait`
  doesn't fail fast, it burns its full timeout. Added the two
  `kubectl create configmap` commands to Quick Start step 4.
- **Eval Job manifests also need `enableServiceLinks: false`** — all six
  `k8s/jobs/*.yaml` manifests were missing this (the chatbot Deployment
  already had it), so Kubernetes' auto-injected `CHROMA_PORT=tcp://...`
  Docker-links env var collided with `AppConfig`'s own `CHROMA_PORT` field
  and crashed every Job instantly. Fixed.
- **RAGAS/DeepEval/promptfoo are now real, live-verified implementations** —
  `run_ragas_eval()` calls `/query` + RAGAS's `evaluate()` per golden-dataset
  item, DeepEval runs its full metric suite, and promptfoo's results are
  actually logged to MLflow (`mlflow_logger.py` gained a real `main()`
  entrypoint). All three have been run against a live cluster with real
  Vertex AI calls; MLflow shows real `ragas_sweep`/`deepeval_sweep`/
  `promptfoo_sweep` runs.
- **The CronJob automation path is now real, not dead stubs** —
  `scripts/run_quality_cycle.py`/`run_safety_cycle.py` are thin
  `kubectl`-based orchestrators (`src/orchestration/k8s_jobs.py`) that
  delete-then-create the real `k8s/jobs/*.yaml` Jobs and block until
  complete; rerun-safety (deleting and recreating, not silently no-opping)
  has been proven live by running each script twice in a row. See
  [docs/known-limitations.md](./docs/known-limitations.md#the-cronjob-automation-path-was-entirely-dead-fixed).
- **PyRIT XPIA, Garak, and Fairlearn are real implementations, live-verified**
  — no longer placeholders. Getting there surfaced four real bugs, all fixed:
  a PyRIT 1.0.0 scorer kwarg rename, a new PyRIT capability-declaration
  requirement that (if left undeclared) would have silently dropped the
  judge's system prompt, a `SelfAskTrueFalseScorer` constructor usage change,
  and garak's `Probe.probe()` needing `_config.reportfile` initialized
  manually when called via its Python API instead of its CLI. Full
  tracebacks and fixes in
  [docs/known-limitations.md](./docs/known-limitations.md#pyrits-orchestrator-api-was-restructured-after-pyrit06).

See [docs/known-limitations.md](./docs/known-limitations.md) for full details.

## Open Decisions

| # | Decision | Blocking |
|---|---|---|
| 1 | Re-check RAGAS for a release newer than 0.4.3 that fixes the broken import | Phase 4 |
| 2 | ~~Verify `claude-3-haiku@20240307` model string on Vertex~~ — resolved: that model ID is retired; the judge tier now defaults to `claude-haiku-4-5` (`CLAUDE_HAIKU_MODEL` env var, `src/chatbot/config.py`), exercised live by RAGAS/DeepEval/promptfoo/PyRIT/Fairlearn judge calls | Done |
| 3 | ~~Confirm LangChain-Vertex wrapper compatibility at RAGAS 0.3.9~~ — resolved: pin `langchain-community<0.4.2` (0.4.2 removed the `chat_models.vertexai` import RAGAS 0.3.9 uses) | Done |
| 4 | ~~Lock golden dataset schema before Phase 3 completes~~ — resolved: schema locked, see `data/golden_dataset.json` and the schema block in `PLAN.md`/`CLAUDE.md` | Done |
| 5 | ~~Define PyRIT XPIA attack loop interface to `/query` endpoint~~ — resolved: `ChatbotQueryTarget`/`ChromaPlantTarget` (real `PromptTarget` subclasses) in `src/redteam/pyrit_xpia.py`, driven by `pyrit.executor.workflow.xpia.XPIATestWorkflow` | Done |
| 6 | ~~Verify `gemini-1.5-flash` still resolves on Vertex~~ — resolved 2026-07: it and every `gemini-2.0-*` variant 404; switched default to `gemini-2.5-flash` (confirmed available, see Known Limitations) | Done |

`.env.example` and `data/golden_dataset.json` still show the retired
`claude-3-haiku@20240307` string in example/sample content only — the actual
default (`src/chatbot/config.py`) and every `k8s/jobs/*.yaml` manifest use
`claude-haiku-4-5`.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for development workflow and
conventions.

## License

MIT — see [LICENSE](./LICENSE).
