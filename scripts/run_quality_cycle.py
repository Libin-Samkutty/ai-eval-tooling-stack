#!/usr/bin/env python3
"""Quality cycle orchestrator — runs RAGAS or DeepEval (alternating) + promptfoo.

This script is the entrypoint for the quality-cycle CronJob. It:
1. Determines which eval framework to use (alternates between RAGAS and DeepEval)
2. Triggers the corresponding Job manifest under k8s/jobs/ and blocks until complete
3. Triggers the promptfoo regression sweep Job and blocks until complete

Each Job manifest already carries its own MLflow logging (see the modules
under src/eval/) — this script only orchestrates via kubectl, it never calls
Vertex AI/Chroma/MLflow itself.

IMPORTANT: Never run concurrently with the safety cycle (MLflow SQLite
write contention).
"""

from __future__ import annotations

from datetime import date

import structlog

from src.orchestration.k8s_jobs import run_job

logger = structlog.get_logger(__name__)


def run_quality_cycle() -> None:
    """Execute a full quality evaluation cycle."""
    # Determine which framework to use (alternates weekly, not daily — the
    # CronJob fires daily, but the same framework runs all 7 days of a given
    # ISO week before switching; see docs/known-limitations.md)
    use_ragas = date.today().isocalendar()[1] % 2 == 0  # Even weeks = RAGAS

    if use_ragas:
        logger.info("quality_cycle_start", framework="ragas")
        run_job("ragas-sweep")
    else:
        logger.info("quality_cycle_start", framework="deepeval")
        run_job("deepeval-sweep")

    logger.info("promptfoo_sweep_start")
    run_job("promptfoo-sweep")

    logger.info("quality_cycle_complete")


if __name__ == "__main__":
    run_quality_cycle()
