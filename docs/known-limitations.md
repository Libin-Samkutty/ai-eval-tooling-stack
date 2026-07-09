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
`historical_balance`-style output as the audited signal.

**Mitigation**: Document the mismatch explicitly. The audit is best-effort
and should not be interpreted as a rigorous fairness certification.

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
