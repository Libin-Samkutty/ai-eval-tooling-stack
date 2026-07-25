# Known Limitations

This document catalogs all accepted limitations in the project. These are
**not bugs** — they are deliberate trade-offs documented for transparency.

## MLflow SQLite Write Contention

**Severity**: Operational
**Component**: MLflow + Eval Jobs

Multiple processes writing to the same SQLite MLflow backend on a PVC will
hit lock contention if eval Jobs run concurrently.

**Mitigation**:
- CronJobs use `concurrencyPolicy: Forbid`
- Quality and safety cycles are scheduled at different times (2 AM vs 4 AM)
- Do not manually trigger eval Jobs while a CronJob is running

**Future resolution**: Upgrade to PostgreSQL backend when scale justifies it.

---

## RAGAS Pinned to 0.3.9

**Severity**: Dependency
**Component**: RAGAS evaluation

`ragas/llms/base.py` (present in 0.3.9 itself, not just 0.4.3) imports
`langchain_community.chat_models.vertexai`. That path was removed in
`langchain_community` **0.4.2** (confirmed by inspecting each release's
wheel contents — present through 0.4.1, absent from 0.4.2 onward; tracked
upstream: GitHub issues #2741, #2745). Because `pyproject.toml` originally
pinned `langchain-community>=0.3.0` with no upper bound, a fresh install
resolved to the latest 0.4.2+ and broke the import even with `ragas==0.3.9`
correctly pinned.

Additionally, 0.3.9 is LangChain-bound throughout — every LLM call goes
through a LangChain wrapper. This is not an oversight.

**Mitigation**:
- Pin to 0.3.9 in `pyproject.toml`
- Pin `langchain-community>=0.3.0,<0.4.2` in `pyproject.toml` — this is the
  actual fix, verified working (import succeeds, `pip check` clean)
- Re-check for newer RAGAS/langchain-community releases before each eval cycle

---

## DVC + Chroma Snapshots

**Severity**: Usability
**Component**: DVC, ChromaDB

Chroma's on-disk format (SQLite + parquet segments) is not meaningfully
diffable. DVC provides blunt-force snapshot versioning for reproducibility;
`dvc diff` output on the vector store will not be useful.

**Mitigation**: Document in `.dvc/config`. Accept that vector store
versioning is snapshot-only, not diff-based.

---

## LangSmith Free Tier Constraints

**Severity**: Operational
**Component**: LangSmith

- **14-day trace retention**: Older traces are automatically deleted.
  Compare eval runs within a 14-day window.
- **5,000 traces/month hard cap**: Traces stop ingesting at the cap, no
  queuing. At this project's volume (~300–400/month), the cap will not be hit.
- **Hosted service**: Traces leave the local cluster. Do not instrument
  with sensitive/PII data.

---

## Fairlearn for Text Generation

**Severity**: Methodological
**Component**: Fairlearn

Fairlearn is built for tabular classifiers, not text generation. We frame
each chatbot answer's Claude-judged POSITIVE/NEGATIVE classification (see
`src/redteam/fairlearn_audit.py`) as the audited signal.

`equalized_odds_difference` is deliberately left `None` rather than computed.
Equalized odds requires real, independent ground-truth labels with both
positive and negative instances per group — there is none for open-ended
answer quality, only the judge's own classification, which is `y_pred`, not
an independent `y_true`. Computing it against a constant `y_true` would be
either degenerate or a no-op restatement of `demographic_parity_difference`.
Only demographic parity is reported.

`EXAMPLE_AUDIT_ITEMS` is 10 items (5 groups × 2), reduced from an earlier
20-item batch once the length-heuristic placeholder was replaced with a real
Claude Haiku judge call — see `docs/api-call-budget.md`.

**Mitigation**: Document the mismatch explicitly. The audit is best-effort
and should not be interpreted as a rigorous fairness certification.

---

## Garak Probes Need an Explicit Prompt Cap; One Probe Is Dropped

**Severity**: Methodological / dependency
**Component**: `src/redteam/garak_probe.py`

The installed `garak` version ships every probe with far more prompts than
a ~10-call safety sub-budget allows — `malwaregen.Evasion` defaults to 48
prompts, `malwaregen.SubFunctions` to 56, etc. Unmodified, the scaffolded
10-probe set costs ~131 calls, not ~10, and this garak version has no
CLI-level prompt-cap flag to bound it externally.

`gcg.GCGCached` (originally scaffolded) also fails to import in the
installed version (`ValueError: Didn't successfully import gcg`, missing an
optional heavy dependency) — replaced with `dan.DAN_Jailbreak`.

Two probes' `recommended_detector`s (`lmrc.SexualContent`,
`realtoxicityprompts.RTPBlank`) default to Google's Perspective API, a paid
external service this project has never used and was never discussed as a
dependency. Both are overridden to local/keyword detectors instead
(`riskywords.SurgeProfanitySexual`, `toxicity.ToxicCommentModel` — the same
local HF model already used for `lmrc.Bullying`) — see `DETECTOR_OVERRIDES`
in `src/redteam/garak_probe.py`.

**Mitigation**: `MAX_PROMPTS_PER_PROBE = 1` samples each probe's prompt list
down (reproducibly, via a seeded `random.Random`) before calling
`Probe.probe()`. This trades probe coverage for budget compliance — the same
tradeoff RAGAS's dataset-size reduction already makes. `toxicity.
ToxicCommentModel` downloads a small HuggingFace model on first use
(`martin-ha/toxic-comment-model`); this is a one-time cost, not a recurring
API call.

---

## No Ingress Controller

**Severity**: Convenience
**Component**: Kubernetes

Access is via `kubectl port-forward` only. No external access, no TLS
termination, no domain routing.

**Mitigation**: Acceptable for single local user. Document port-forward
commands in Makefile.

---

## No Argo Workflows/CD

**Severity**: Automation
**Component**: Kubernetes

Argo's controller overhead only pays off with real DAG parallelism. At this
tier, sequential Job scheduling via scripts is sufficient.

**Mitigation**: Use CronJobs with `concurrencyPolicy: Forbid` and script-based
orchestration.

---

## No Prometheus/Grafana

**Severity**: Observability
**Component**: Monitoring

No traffic pattern worth graphing at this scale. MLflow provides metric
tracking; LangSmith provides trace visualization.

**Mitigation**: Add Prometheus/Grafana only when traffic patterns justify
real-time dashboards.

---

## RAGAS/DeepEval Alternation is Weekly, Not Daily

**Severity**: Behavioral
**Component**: `scripts/run_quality_cycle.py`

The quality-cycle `CronJob` fires **daily**, but the RAGAS/DeepEval
alternation is keyed off the ISO week number
(`date.today().isocalendar()[1] % 2 == 0`), not the day. This means the
**same** framework runs every day for a full calendar week before switching
to the other — e.g. RAGAS runs all 7 days of an even week, then DeepEval
runs all 7 days of the next odd week.

**Mitigation**: This is intentional, not an oversight — recorded here so it
isn't mistaken for a bug. If day-to-day alternation is ever wanted instead,
swap the key for `date.today().toordinal() % 2`.

---

## CronJobs Are Incompatible With Codespaces

**Severity**: Operational (cost)
**Component**: `k8s/cronjobs/`, GitHub Codespaces

`quality-cycle` and `safety-cycle` assume an always-on cluster. GitHub
Codespaces bills for wall-clock VM time regardless of what's running inside,
and auto-stops after an idle timeout based on whether a client (VS Code,
`gh codespace ssh`, etc.) is connected — not on CPU/process activity. Two
failure modes follow directly from that:

- If the Codespace is disconnected (the common case), it auto-stops long
  before a 2 AM/4 AM schedule fires, so the CronJob silently never runs.
- If a connection is kept open 24/7 specifically to make the schedule fire,
  a 4-core Codespace burns the entire 120 free core-hours/month in about 30
  wall-clock hours (~1.25 days).

**Mitigation**:
- `k8s/cronjobs/*.yaml` are reference manifests for a persistent-cluster
  deployment target only. Never `kubectl apply` them inside a Codespace.
- `make eval-quality` / `make eval-safety` (and their `-wait` variants) refuse
  to run if any CronJob is found on the cluster (`guard-no-cron` target).
- Trigger cycles on demand instead: `make eval-quality-wait` /
  `make eval-safety-wait` inside the Codespace, or
  `python scripts/run_cycle_and_stop.py quality` from your local machine,
  which SSHes in, blocks until the cycle's Jobs finish, and stops the
  Codespace immediately after — success or failure.
- No workflow, CI job, or prebuild config in this repo creates or starts a
  Codespace automatically (verified: nothing in `.github/workflows`
  references `codespace`, and there is no `.devcontainer/` prebuild config).
  The only supported way to start one is a local `gh codespace ssh` /
  `scripts/run_cycle_and_stop.py` invocation. This can't prevent a human from
  clicking "Create codespace" on github.com or in an IDE's Codespaces
  extension — that's a GitHub account-level action, not something the repo
  controls.

---

## Codespace Disk Space Exhaustion During `make build-eval`

**Severity**: Operational (build failure)
**Component**: `Dockerfile.eval`, GitHub Codespaces

The default Codespace disk is 32GB. `Dockerfile.eval` installs the `.[all]`
extras (ragas, deepeval, pyrit, garak, fairlearn), which pull in torch and
`nvidia-cu13-*` CUDA wheels — dead weight on this CPU-only `kind` cluster,
but `pip` has no way to know that from the dependency spec alone. Combined
with the `kindest/node` image, the already-built chatbot/mlflow images, and
Docker's build cache, disk usage was already at 26GB/32GB before
`make build-eval` ran; the build failed partway through downloading `torch`
with `OSError: [Errno 28] No space left on device`.

**What was tried, in order, verified 2026-07-10** (this ran through five
separate `no space left on device` failures before landing on a fix that
held — each item below is a real, tested data point, not a hypothesis):

1. `docker builder prune -af && docker image prune -af` before building
   (host-level copies of already-`kind load`ed images are redundant — the
   node's containerd store has its own copy). Recovered ~6GB (4GB → 10GB
   free) — **not enough alone**; a retry still failed on `torch` with the
   same `OSError`.
2. **Removing preinstalled language SDKs did nothing.** The default
   Codespace base image ships `/usr/share/dotnet`, `/usr/local/sdkman`,
   `/usr/local/go`, `/usr/local/rvm`, `/usr/local/php` (~2.5GB combined),
   unused by this Python-only project. `sudo rm -rf` on them succeeds (files
   are gone from `ls`), but `df` reports **byte-for-byte identical**
   available space before and after — these directories are part of the
   Codespace's read-only base image layer; deleting the merged overlayfs
   view doesn't free the underlying (shared, immutable) blocks. Don't spend
   time on this path.
3. `kind delete cluster --name eval-stack` before building (the cluster's
   containerd-storage Docker volume alone was 6.5GB). Freed 9.5GB → 16.9GB
   available — helped, but a build combining the full Python ML stack
   *and* promptfoo's npm/onnxruntime deps in one image still failed 3 more
   times afterward, each on a different large file (a musl-target binary,
   an onnxruntime CUDA `.so`, then a plain small `.py` file — i.e. the
   *specific* culprit stopped being the point; there just wasn't enough
   total headroom for the combined image at all).
4. Stripping promptfoo's GPU-only `onnxruntime-node` binaries (linux-x64
   CPU is the only combination that ever runs here) — real savings, but
   the same npm install is not version-pinned (`npm install -g promptfoo`
   with no `@version`), so this dependency isn't even guaranteed to be
   present build-to-build; the fix has to be conditional (`if [ -d ... ]`)
   or it can crash the whole `RUN` on a build where the directory doesn't
   exist at all.
5. **What actually fixed it**: split `Dockerfile.eval` into two images —
   `Dockerfile.eval` (git + the Python `.[all]` ML stack: ragas, deepeval,
   pyrit, garak, fairlearn) and `Dockerfile.promptfoo` (curl/nodejs/npm/
   promptfoo + base Python deps only). No single `docker build` ever needs
   both footprints in disk at once, which is what a 32GB Codespace disk
   couldn't sustain. `k8s/jobs/promptfoo-sweep.yaml` now points at
   `oss-ai-eval-promptfoo:latest`; the other five Job manifests still use
   `oss-ai-eval-jobs:latest`.
6. **If disk ever reaches 100% (0 bytes available)** — this happened once,
   from accumulated build-cache across several failed attempts — a plain
   `docker builder prune -af` may not recover enough. Use
   `docker system prune -af --volumes` (safe as long as no cluster/
   container you need is currently running; it removes *all* stopped
   containers, unused networks, unused images, and all build cache). This
   recovered the full 19.75GB that five failed builds' caches had pinned.
7. **Resolved** (2026-07-10): added `RUN pip install torch --index-url
   https://download.pytorch.org/whl/cpu` as its own layer in
   `Dockerfile.eval`, *before* `pip install -e ".[all]"` — torch is only a
   transitive dependency (pulled in by pyrit/deepeval/garak, not listed
   directly in `pyproject.toml`), so this is a Dockerfile-level fix, not a
   `pyproject.toml` pin change. Once torch is already present satisfying
   the transitive `torch>=X` specs, the later `.[all]` resolve never
   reaches for PyPI's default (CUDA-bundling) wheel. Verified: `import
   torch; torch.__version__` reports `2.13.0+cpu`, `torch.cuda.is_available()`
   is `False`, and the full `.[all]` install + export/unpack finally
   completed cleanly (previously failed 4 times in a row on CUDA `.so`
   files specifically).

**Update (2026-07-15)**: the same disk-headroom problem resurfaced when
rebuilding `oss-ai-eval-jobs` after a code fix — building on a Codespace
with a live `kind` cluster already loaded tops out around 3.4GB free no
matter how much `docker builder prune -af`/`docker system prune -af
--volumes` is run beforehand, because the cluster's own containerd store
(~13GB) is in active use and can't be reclaimed by a prune. The fix that
actually worked: prune the build cache **again, immediately before
`kind load`**, not just before/after `docker build` — the load step needs
its own scratch space to import into the node's containerd, separate from
whatever the build itself used. When that still wasn't enough, deleting and
recreating the `kind` cluster (freeing the full containerd store) landed
disk back in the ~16-17GB-free range where the build reliably succeeds.

---

## `Dockerfile.eval` Was Missing `git`, Breaking `import ragas`

**Severity**: Build correctness (fixed)
**Component**: `Dockerfile.eval`

RAGAS 0.3.9's `ragas/__init__.py` imports `ragas.experiment`, which does
`import git` (GitPython) unconditionally at module load — not lazily, not
behind a try/except. GitPython raises `ImportError: Failed to initialize:
Bad git executable` if the `git` binary isn't on `$PATH`, which it wasn't:
`Dockerfile.eval`'s `apt-get install` line only installed
`curl nodejs npm`. The result: `import ragas` — not any RAGAS *usage*, just
the bare import — crashed in every eval Job built from this image. This
would have surfaced the first time `eval-ragas` actually ran, not at build
time, since `pip install` doesn't exercise the package's import path.

**Fix**: added `git` to the `apt-get install` line in `Dockerfile.eval`.
Verified by running `python -c "import ragas"` inside the built image.

---

## `Dockerfile.promptfoo`'s apt-Provided Node.js Was Too Old for promptfoo

**Severity**: Build correctness (fixed)
**Component**: `Dockerfile.promptfoo`

Debian's `nodejs`/`npm` apt packages (as shipped in the `python:3.11-slim`
base image) resolve to Node **20.19.2**. `npm install -g promptfoo`
succeeds anyway — `EBADENGINE` is only a warning at install time — but
promptfoo (installed unpinned, i.e. whatever "latest" happens to be)
currently hard-requires Node `^20.20.0 || >=22.22.0` *at runtime*:
`npx promptfoo --version` (and `npx promptfoo eval`, which the Job actually
calls) refuses to run at all on 20.19, printing "promptfoo requires a
supported Node.js runtime" and exiting non-zero. This would have failed
the `promptfoo-sweep` Job every time, silently, since the image still
builds successfully — the failure only shows up when the container runs.

**Fix**: install Node via NodeSource's setup script (`setup_22.x`) instead
of the distro package, in the same `RUN` as before:
```bash
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y --no-install-recommends nodejs
```
Verified by running `npx promptfoo --version` inside the built image.

**Note**: since `promptfoo` is installed without a version pin, this is a
moving target — a future promptfoo release could raise its Node
requirement again, or this project's Node major version could itself go
end-of-life. Re-verify `npx promptfoo --version` runs cleanly whenever this
image is rebuilt after a while.

---

## Running a Partially-Unpacked Docker Image Balloons Disk Usage

**Severity**: Operational (data-integrity + disk)
**Component**: Docker/containerd, GitHub Codespaces

A `docker build` that fails during the final "exporting to image" /
"unpacking to containerd" step (e.g. from running out of disk, see
[Codespace Disk Space Exhaustion](#codespace-disk-space-exhaustion-during-make-build-eval))
can still leave a **tagged, seemingly-normal image** behind — `docker
images` shows it, `docker run` against it can even start a container and
execute code, because most layers unpacked fine and only one broken/unused
file failed (in one observed case, an irrelevant musl-target binary bundled
in promptfoo's `node_modules`, never touched on this glibc/Debian base).

The danger: each `docker run` against that image appears to make containerd
retry completing the broken snapshot, and the retry's partial writes are
not cleaned up on failure. Two `docker run` invocations against one such
image took its reported size from 5.22GB to **16.9GB** with no explicit
build step in between — and pushed the Codespace from 11.7GB free to 213MB
free (100% disk used) in the process.

**Mitigation**:
- Treat any image from a `docker build` that printed `ERROR: failed to
  build` / `failed to extract layer` as unusable, even if it got tagged.
  `docker rmi -f <image>` it immediately — do not `docker run` it to "check"
  whether it's fine, that's what caused the disk spike here.
- Fix the underlying build failure (usually disk space) and rebuild clean
  before running anything from the new image.
- Watch `df -h /` after any build that reports an export/unpack error.

**Update (2026-07-15)**: the same failure mode occurs one level up during
`kind load docker-image` — a load that fails partway (e.g. disk exhausted
mid-import into the node's containerd) leaves the node's containerd
snapshot store in a similarly bad state. Same mitigation applies: don't
retry `kind load` against a load that already failed without freeing disk
first; prune, then retry clean.

---

## Query Condensation Adds LLM Calls

**Severity**: Cost
**Component**: Multi-turn chat

Each non-first turn in a multi-turn conversation adds one Gemini call for
query condensation (rewriting follow-ups into standalone questions).

**Mitigation**: Account for this in API call budgets. Interactive dev traffic
is not counted in cycle budgets.

---

## promptfoo MLflow Integration is Custom

**Severity**: Maintenance
**Component**: promptfoo, MLflow

promptfoo outputs JSON/CSV natively but does not log to MLflow. A custom
Python wrapper (`src/eval/mlflow_logger.py`) reads promptfoo output and
calls `mlflow.log_metrics`.

**Mitigation**: Maintain the wrapper as promptfoo output format evolves.

---

## Single-Node Cluster

**Severity**: Resilience
**Component**: Kubernetes (kind)

kind provides a single-node cluster. No high availability, no pod
rescheduling on node failure.

**Mitigation**: Acceptable for local development. Eval Jobs are ephemeral
and re-runnable. Standing deployments have `replicas: 1`.

---

## `ragas_eval.py`'s Core Evaluation Function Was an Unimplemented Stub

**Severity**: Functional gap (fixed)
**Component**: `src/eval/ragas_eval.py`

`run_ragas_eval()` used to build an empty `RAGASResult` per item without
ever calling the chatbot's `/query` endpoint or RAGAS's `evaluate()` — the
Job still reported `Complete` in under a second with zero real work.

**Fix**: `run_ragas_eval()` now calls `/query` per golden-dataset item,
builds `SingleTurnSample`s from the answer + retrieved sources, and runs
real `ragas.evaluate()` with `ContextPrecision`/`Faithfulness`/
`AnswerRelevancy`, judged by `ChatAnthropicVertex` (Claude Haiku on Vertex
AI Model Garden — not the plain `ChatVertexAI` class, which is Gemini-only).
`EVAL_DATASET_SIZE` is reduced from 20 to 10 specifically for this eval to
keep the real LLM-judged Context Precision metric (5 judge calls/question
on its own) under the 200-call hard cap — see `docs/api-call-budget.md`.

---

## `promptfoo-sweep`'s MLflow Logging Step Was a Silent No-Op

**Severity**: Bug (fixed)
**Component**: `k8s/jobs/promptfoo-sweep.yaml`, `src/eval/mlflow_logger.py`

`mlflow_logger.py` had no `if __name__ == "__main__":`/argparse, so `python
-m src.eval.mlflow_logger --promptfoo-output ...` just imported the module
and exited 0 — `log_promptfoo_results()` was never called, and promptfoo's
genuinely-real pass/fail results were thrown away when the Job's `emptyDir`
was torn down.

**Fix**: added a `main()` entrypoint (argparse, `--promptfoo-output`
required) scoped narrowly to the promptfoo case — `ragas_eval.py`/
`deepeval_eval.py` already call their own logging functions in-process and
never need this CLI, so no generic `--mode` dispatch was added (Rule of
Three: one real caller today). All three `log_*_results` functions also now
log `judge_model`/`dataset_size` params and `framework`/`cycle_type`/
`git_commit` tags for MLflow-UI searchability.

---

## promptfoo Test Questions Don't Match the Seeded Golden Dataset's Topics

**Severity**: Test-data mismatch (not a chatbot bug)
**Component**: `promptfoo/promptfooconfig.yaml`, `scripts/seed_chroma.py`

`promptfoo-sweep`'s 80% fail rate (verified: 12/15 failed, 1 error) is
mostly not the chatbot misbehaving — it's correctly saying "the provided
context does not contain information about X" for questions like "What is
machine learning?", "Explain neural networks", "What are transformers in
NLP?". The seeded Chroma documents (`scripts/seed_chroma.py`) cover RAG,
RAGAS, vector embeddings, ChromaDB, and prompt injection — not general ML
concepts — so there's nothing in the retrieved context to answer with, and
the chatbot's honest "I don't know" gets graded as a failure against a
promptfoo test config that expects those topics to be answerable.

There is also one genuine config bug that was fixed separately: one test
case's grader was configured with `vertex:claude-3-haiku@20240307` for a
similarity-based check, which requires an *embedding* model —
`claude-3-haiku` is a chat model, not an embedding model, and that model ID
is now retired anyway (see `promptfooconfig.yaml`'s judge, updated to
`vertex:claude-haiku-4-5`).

**Mitigation**: none yet — flagging for whoever aligns the two. Either
broaden the seeded documents to cover the topics `promptfooconfig.yaml`
tests, narrow the test questions to match what's actually seeded, or both.

---

## The CronJob Automation Path Was Entirely Dead (fixed)

**Severity**: Functional gap (fixed)
**Component**: `scripts/run_quality_cycle.py`, `scripts/run_safety_cycle.py`,
`k8s/cronjobs/`

`run_quality_cycle.py`/`run_safety_cycle.py` (what the two CronJobs actually
invoke) were log-only stubs — `structlog.info(...)` calls with
`TODO(phase-4)`/`TODO(phase-6)` comments, no calls into `src/eval/` or
`src/redteam/` at all. Even if they had been implemented in-process, both
CronJob manifests pointed `image:` at `oss-ai-eval-chatbot:latest`
(`Dockerfile.chatbot`), which has neither the eval/redteam extras nor even
`scripts/` copied in — the container would `FileNotFoundError` before
reaching any Python import error. Only the standalone `k8s/jobs/*.yaml` +
`make eval-*` path (correctly imaged) ever actually worked.

**Fix**: rather than reimplementing eval/redteam logic inline (which would
need a single mega-image with every dependency — the exact disk-exhaustion
problem `Dockerfile.eval`/`Dockerfile.promptfoo` were split to avoid), the
two scripts are now thin `kubectl`-based orchestrators
(`src/orchestration/k8s_jobs.py`) that delete-then-create the *existing*,
correctly-imaged `k8s/jobs/*.yaml` manifests and block until each completes.
A new minimal `Dockerfile.orchestrator` (pinned `kubectl` + `structlog`
only, no eval deps) backs the CronJob pods, authorized via a narrowly-scoped
`k8s/rbac/eval-orchestrator-rbac.yaml` ServiceAccount/Role/RoleBinding
(create/get/list/watch/delete on `batch/jobs` only). This does not change
the [CronJobs-incompatible-with-Codespaces](#cronjobs-are-incompatible-with-codespaces)
guidance above — the orchestrator scripts were verified by running them
directly (`python scripts/run_quality_cycle.py`), never by applying an
actual CronJob object in a Codespace.

---

## PyRIT's Orchestrator API Was Restructured After `pyrit>=0.6`

**Severity**: Dependency
**Component**: `src/redteam/pyrit_xpia.py`, `pyproject.toml` (`pyrit>=0.4.0`)

`pyrit.orchestrator.XPIAOrchestrator`, referenced in this module's original
TODO scaffolding, no longer exists in the installed version (`pyrit==0.14.0`
at time of writing) — `pyrit.orchestrator` isn't even an importable module
anymore. PyRIT restructured XPIA support into
`pyrit.executor.workflow.xpia.XPIATestWorkflow`, paired with
`pyrit.score.SelfAskTrueFalseScorer` for judging and
`pyrit.setup.initialize_pyrit_async(...)` for the now-required explicit
memory-backend initialization.

**Mitigation**: `pyrit_xpia.py` targets the current API. Since
`pyproject.toml` pins only a floor (`pyrit>=0.4.0`, no ceiling), re-verify
the target API (`python -c "from pyrit.executor.workflow.xpia import
XPIATestWorkflow"`) before upgrading pyrit, in case it moves again.

**Update (live verification)**: it moved again, within days. The local dev
venv had `pyrit==0.14.0`, but the `oss-ai-eval-jobs` image — built fresh in
the Codespace from the same no-ceiling `pyrit>=0.4.0` pin — resolved
`pyrit==1.0.0`, which renamed `SelfAskTrueFalseScorer`'s
`true_false_question` kwarg to `question`. First surfaced when
`pyrit-xpia`'s first live run crashed instantly with `TypeError:
SelfAskTrueFalseScorer.__init__() got an unexpected keyword argument
'true_false_question'`. Fixed by using `question=` and bumping the floor to
`pyrit>=1.0.0` (and upgrading the local venv to match, so local `mypy`
checks the same API the Job actually runs). `XPIATestWorkflow.__init__` and
`.execute_async(attack_content=..., processing_prompt=...)` were unaffected
by the 1.0.0 bump — confirmed via `inspect.signature` against both the local
venv and a throwaway `kubectl run` debug pod using the actual cluster image.

**Second update (same live run, next failure)**: fixing the kwarg rename
surfaced a deeper 1.0.0 behavior change. `SelfAskTrueFalseScorer` validates
its `chat_target` against `TARGET_REQUIREMENTS` (`supports_multi_turn` +
`supports_editable_history`) at construction time — new in 1.0.0's
capability-declaration system (`pyrit.prompt_target.common.target_*`), which
didn't exist in 0.14.0. `ClaudeVertexJudgeTarget` never declared any
capabilities, so it fell back to the all-`False` base default and
construction raised `ValueError: Target does not satisfy 2 required
capability(ies)`. Fixed by giving it a `_DEFAULT_CONFIGURATION` (modeled on
PyRIT's own `OpenAIChatTarget`, which declares `supports_multi_turn=True,
supports_editable_history=True, supports_system_prompt=True` — a legitimate
native capability for any target wrapping a chat-completions-style API,
not an adaptation). Declaring the capability without also using it would
have been a silent correctness bug: the scorer calls
`chat_target.set_system_prompt(...)` before sending the question, and once
the target claims `supports_system_prompt`/`supports_multi_turn`, the
normalization pipeline stops squashing history and passes the full
conversation (system message included) to `_send_prompt_to_target_async`.
The original implementation only ever read
`normalized_conversation[-1]` (the last message), which would have silently
dropped the system prompt carrying the actual true/false question — every
judgment would run with no instructions. Rewrote
`_send_prompt_to_target_async` to walk every message/piece, route
`role == "system"` to Claude's separate `system=` param and everything else
into `messages=[...]`, mapping `assistant`/`simulated_assistant` roles to
Claude's `"assistant"`.

**Third update (same live run)**: fixing the capability declaration surfaced
one more issue, this time in `SelfAskTrueFalseScorer.__init__` itself:
passing `question=` without also passing `system_prompt=` raises
`ValueError: system_prompt and question must be provided together` — the
1.0.0 constructor only auto-renders the default rubric when *both* are
omitted. The classmethod `SelfAskTrueFalseScorer.from_question(chat_target=,
question=)` exists specifically to render the system prompt from a
`TrueFalseQuestion` and supply both together; switched to it instead of the
raw constructor.

---

## Garak's `Probe.probe()` Needs `_config.reportfile` Set Manually

**Severity**: Bug (found during live Codespace verification, now fixed)
**Component**: `src/redteam/garak_probe.py`

`garak.probes.base.Probe.probe()` unconditionally writes each attempt to
`_config.reportfile.write(...)`. Normally `garak/cli.py` opens this file
during its own startup; this module calls `Probe.probe()` directly (see the
module docstring for why — no prompt-cap CLI flag exists), bypassing that
setup entirely, so `_config.reportfile` stays `None` and the first probe
crashes with `AttributeError: 'NoneType' object has no attribute 'write'`.

**Mitigation**: `run_garak_probes()` now opens a throwaway
`/tmp/garak_report.jsonl` and assigns it to `garak._config.reportfile`
before running any probes (mirroring `cli.py`'s own
`_config.reportfile = open(...)` line). This module never reads that file —
results are extracted directly from the returned `attempts` list — so its
contents are discarded; it exists purely to satisfy garak's global-state
assumption that a CLI run initialized it.

---

## Eval Job Manifests Needed `enableServiceLinks: false` Too

**Severity**: Bug (found during live Codespace verification, now fixed)
**Component**: `k8s/jobs/*.yaml`

`k8s/chatbot-deployment.yaml` already sets `enableServiceLinks: false` on
its pod spec, but all six `k8s/jobs/*.yaml` Job manifests did not. Kubernetes
auto-injects legacy Docker-links-style environment variables for every
Service active in the namespace (`{SVCNAME}_PORT`, e.g.
`CHROMA_PORT=tcp://10.96.101.31:8001`) unless `enableServiceLinks: false` is
set. This collided with `src/chatbot/config.py`'s own `CHROMA_PORT` field
(`int(os.environ.get("CHROMA_PORT", "8001"))`), which every Job crashes on
at `AppConfig()` construction even though most Jobs never talk to Chroma
directly — `AppConfig` unconditionally builds the full config. First
surfaced when `ragas-sweep`'s first live run failed instantly with
`ValueError: invalid literal for int() with base 10: 'tcp://...'`.

**Mitigation**: added `enableServiceLinks: false` next to `restartPolicy:
Never` in all six `k8s/jobs/*.yaml` pod specs, matching the chatbot
Deployment. Any future Job/Deployment manifest that imports `AppConfig`
needs this too.

---

## `deepeval-sweep`'s First Live Attempt Hit an `httpx.ReadTimeout`

**Severity**: Environmental (not a code defect)
**Component**: `src/eval/deepeval_eval.py`, live Codespace verification

On `deepeval-sweep`'s first-ever standalone run against the live cluster, one
of the 20 `/query` calls raised `httpx.ReadTimeout` partway through the sweep.
This was not the bare-5s-default timeout bug already fixed in the redteam
modules in a prior session — `deepeval_eval.py` already uses a 30s httpx
timeout. The chatbot was genuinely slow to respond under sustained load on
the Codespace's shared, resource-constrained VM at that moment.

**Mitigation**: none needed — Kubernetes' own Job-level `backoffLimit` retry
handled it automatically; the retried attempt completed cleanly and all 20
items were logged to MLflow. No code change. If this recurs frequently
(rather than as a one-off), consider raising the httpx timeout further or
adding an explicit retry-with-backoff inside `deepeval_eval.py` itself rather
than relying solely on the Job restart.
