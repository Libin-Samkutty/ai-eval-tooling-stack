"""Run the existing k8s/jobs/*.yaml Job manifests sequentially via kubectl.

Used by scripts/run_quality_cycle.py and scripts/run_safety_cycle.py to
trigger the same, correctly-imaged Job manifests that `make eval-*` applies
on demand, but sequentially and blocking — this is what a CronJob would do.
Never touches Vertex AI, Chroma, or MLflow directly, only kubectl, so it can
run from a minimal image (see Dockerfile.orchestrator) regardless of which
eval/redteam extras the target Job's own image installs.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

JOBS_DIR = Path(__file__).resolve().parent.parent.parent / "k8s" / "jobs"


def run_job(job_name: str, timeout: str = "45m") -> None:
    """Delete any existing Job with this name, create it fresh, and block until complete.

    Jobs are immutable once created, so a completed Job with the same name
    from a prior run must be deleted first — `kubectl apply` would otherwise
    silently no-op against it instead of re-running.
    """
    manifest_path = JOBS_DIR / f"{job_name}.yaml"

    logger.info("job_deleting", job=job_name)
    subprocess.run(
        [
            "kubectl",
            "delete",
            "job",
            job_name,
            "--ignore-not-found",
            "--wait=true",
            "--cascade=foreground",
        ],
        check=True,
    )

    logger.info("job_creating", job=job_name, manifest=str(manifest_path))
    subprocess.run(["kubectl", "create", "-f", str(manifest_path)], check=True)

    logger.info("job_wait_start", job=job_name, timeout=timeout)
    subprocess.run(
        ["kubectl", "wait", "--for=condition=complete", f"--timeout={timeout}", f"job/{job_name}"],
        check=True,
    )
    logger.info("job_complete", job=job_name)
