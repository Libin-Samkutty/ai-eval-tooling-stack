#!/usr/bin/env python3
"""Safety cycle orchestrator — runs PyRIT XPIA, Garak probes, Fairlearn audit.

This script is the entrypoint for the safety-cycle CronJob. It runs all
safety evaluations sequentially to avoid MLflow SQLite write contention.

IMPORTANT: Never run concurrently with the quality cycle.
"""

from __future__ import annotations

import asyncio

import structlog

logger = structlog.get_logger(__name__)


async def run_safety_cycle() -> None:
    """Execute a full safety evaluation cycle."""
    # 1. PyRIT XPIA
    logger.info("safety_cycle_start", component="pyrit_xpia")
    # TODO(phase-6): Run XPIA orchestrator and log results

    # 2. Garak probes
    logger.info("safety_cycle_component", component="garak")
    # TODO(phase-6): Run Garak probes and log results

    # 3. Fairlearn audit
    logger.info("safety_cycle_component", component="fairlearn")
    # TODO(phase-6): Run Fairlearn audit and log results

    logger.info("safety_cycle_complete")


if __name__ == "__main__":
    asyncio.run(run_safety_cycle())
