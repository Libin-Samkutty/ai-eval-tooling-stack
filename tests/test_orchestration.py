"""Tests for the kubectl-based Job orchestration used by the cycle scripts."""

from __future__ import annotations

from datetime import date
from unittest.mock import call, patch

import pytest

# ── run_job ────────────────────────────────────────────


def test_run_job_calls_delete_create_wait_in_order():
    """run_job deletes, creates, then waits, in that order."""
    from src.orchestration.k8s_jobs import JOBS_DIR, run_job

    with patch("src.orchestration.k8s_jobs.subprocess.run") as mock_run:
        run_job("ragas-sweep")

    manifest_path = str(JOBS_DIR / "ragas-sweep.yaml")
    assert mock_run.call_args_list == [
        call(
            [
                "kubectl",
                "delete",
                "job",
                "ragas-sweep",
                "--ignore-not-found",
                "--wait=true",
                "--cascade=foreground",
            ],
            check=True,
        ),
        call(["kubectl", "create", "-f", manifest_path], check=True),
        call(
            ["kubectl", "wait", "--for=condition=complete", "--timeout=45m", "job/ragas-sweep"],
            check=True,
        ),
    ]


def test_run_job_propagates_kubectl_failure():
    """A failing kubectl invocation (e.g. delete) aborts the sequence."""
    import subprocess

    from src.orchestration.k8s_jobs import run_job

    with patch("src.orchestration.k8s_jobs.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, ["kubectl"])
        with pytest.raises(subprocess.CalledProcessError):
            run_job("ragas-sweep")

    mock_run.assert_called_once()


# ── week-parity framework selection ───────────────────


def test_quality_cycle_selects_ragas_on_even_week():
    """Even ISO weeks trigger the RAGAS sweep, not DeepEval."""
    from scripts.run_quality_cycle import run_quality_cycle

    with (
        patch("scripts.run_quality_cycle.date") as mock_date,
        patch("scripts.run_quality_cycle.run_job") as mock_run_job,
    ):
        mock_date.today.return_value = date(2026, 1, 5)  # ISO week 2 (even)
        run_quality_cycle()

    assert mock_run_job.call_args_list == [call("ragas-sweep"), call("promptfoo-sweep")]


def test_quality_cycle_selects_deepeval_on_odd_week():
    """Odd ISO weeks trigger the DeepEval sweep, not RAGAS."""
    from scripts.run_quality_cycle import run_quality_cycle

    with (
        patch("scripts.run_quality_cycle.date") as mock_date,
        patch("scripts.run_quality_cycle.run_job") as mock_run_job,
    ):
        mock_date.today.return_value = date(2026, 1, 12)  # ISO week 3 (odd)
        run_quality_cycle()

    assert mock_run_job.call_args_list == [call("deepeval-sweep"), call("promptfoo-sweep")]


def test_safety_cycle_runs_all_three_in_order():
    """Safety cycle runs pyrit, then garak, then fairlearn."""
    from scripts.run_safety_cycle import run_safety_cycle

    with patch("scripts.run_safety_cycle.run_job") as mock_run_job:
        run_safety_cycle()

    assert mock_run_job.call_args_list == [
        call("pyrit-xpia"),
        call("garak-probe"),
        call("fairlearn-audit"),
    ]
