#!/usr/bin/env python3
"""Safety cycle orchestrator — runs PyRIT XPIA, Garak probes, Fairlearn audit.

This script is the entrypoint for the safety-cycle CronJob. It triggers the
three redteam Job manifests under k8s/jobs/ sequentially, blocking on each
in turn, to avoid MLflow SQLite write contention. Each Job manifest already
carries its own MLflow logging (see the modules under src/redteam/) — this
script only orchestrates via kubectl, it never calls Vertex AI/Chroma/MLflow
itself.

IMPORTANT: Never run concurrently with the quality cycle.
"""

from __future__ import annotations

import structlog

from src.orchestration.k8s_jobs import run_job

logger = structlog.get_logger(__name__)


def run_safety_cycle() -> None:
    """Execute a full safety evaluation cycle."""
    logger.info("safety_cycle_start", component="pyrit_xpia")
    run_job("pyrit-xpia")

    logger.info("safety_cycle_component", component="garak")
    run_job("garak-probe")

    logger.info("safety_cycle_component", component="fairlearn")
    run_job("fairlearn-audit")

    logger.info("safety_cycle_complete")


if __name__ == "__main__":
    run_safety_cycle()
