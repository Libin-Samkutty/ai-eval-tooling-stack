#!/usr/bin/env python3
"""Quality cycle orchestrator — runs RAGAS or DeepEval (alternating) + promptfoo.

This script is the entrypoint for the quality-cycle CronJob. It:
1. Determines which eval framework to use (alternates between RAGAS and DeepEval)
2. Runs the selected framework
3. Runs promptfoo regression sweep
4. Logs all results to MLflow

IMPORTANT: Never run concurrently with the safety cycle (MLflow SQLite
write contention).
"""

from __future__ import annotations

import asyncio

import structlog

logger = structlog.get_logger(__name__)


async def run_quality_cycle() -> None:
    """Execute a full quality evaluation cycle."""
    # Determine which framework to use (alternates weekly, not daily — the
    # CronJob fires daily, but the same framework runs all 7 days of a given
    # ISO week before switching; see docs/known-limitations.md)
    from datetime import date

    use_ragas = date.today().isocalendar()[1] % 2 == 0  # Even weeks = RAGAS

    if use_ragas:
        logger.info("quality_cycle_start", framework="ragas")
        # TODO(phase-4): Call run_ragas_eval and log to MLflow
    else:
        logger.info("quality_cycle_start", framework="deepeval")
        # TODO(phase-4): Call run_deepeval_eval and log to MLflow

    # Run promptfoo sweep
    logger.info("promptfoo_sweep_start")
    # TODO(phase-4): Run promptfoo and log results via mlflow_logger

    logger.info("quality_cycle_complete")


if __name__ == "__main__":
    asyncio.run(run_quality_cycle())
