"""MLflow logging wrapper — bridges eval tool outputs to MLflow.

promptfoo outputs JSON/CSV natively. This module reads those outputs
and logs them as MLflow metrics. This is NOT automatic — it's a custom
glue layer.

Also used by RAGAS and DeepEval eval scripts to log their results.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import mlflow
import structlog

logger = structlog.get_logger(__name__)


def init_mlflow(tracking_uri: str, experiment_name: str = "oss-ai-eval-stack") -> None:
    """Initialize MLflow tracking connection.

    Args:
        tracking_uri: MLflow tracking server URI.
        experiment_name: MLflow experiment to log to.
    """
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(experiment_name)
    logger.info("mlflow_initialized", tracking_uri=tracking_uri, experiment=experiment_name)


def _tag_common(framework: str, judge_model: str | None) -> None:
    """Set the tags shared by all three log_*_results functions."""
    mlflow.set_tag("framework", framework)
    mlflow.set_tag("cycle_type", "quality")
    mlflow.set_tag("git_commit", os.environ.get("GIT_COMMIT", "unknown"))
    if judge_model:
        mlflow.log_param("judge_model", judge_model)


def log_ragas_results(
    results: list[dict[str, Any]],
    run_name: str = "ragas_sweep",
    judge_model: str | None = None,
) -> None:
    """Log RAGAS evaluation results to MLflow.

    Args:
        results: List of result dicts with metric values.
        run_name: Name for the MLflow run.
        judge_model: The Claude model used as the RAGAS judge LLM, logged
            as a param for reproducibility.
    """
    with mlflow.start_run(run_name=run_name):
        _tag_common("ragas", judge_model)
        mlflow.log_param("dataset_size", len(results))

        # Aggregate metrics
        metric_keys = ["context_precision", "faithfulness", "answer_relevancy"]
        for key in metric_keys:
            values = [r[key] for r in results if r.get(key) is not None]
            if values:
                avg = sum(values) / len(values)
                mlflow.log_metric(f"ragas_{key}_mean", avg)
                mlflow.log_metric(f"ragas_{key}_count", len(values))

        # Log raw results as artifact
        mlflow.log_dict(results, "ragas_results.json")
        logger.info("ragas_logged_to_mlflow", run_name=run_name, result_count=len(results))


def log_deepeval_results(
    results: list[dict[str, Any]],
    run_name: str = "deepeval_sweep",
    judge_model: str | None = None,
) -> None:
    """Log DeepEval evaluation results to MLflow.

    Args:
        results: List of result dicts with metric values.
        run_name: Name for the MLflow run.
        judge_model: The Claude model used as the DeepEval judge LLM,
            logged as a param for reproducibility.
    """
    with mlflow.start_run(run_name=run_name):
        _tag_common("deepeval", judge_model)
        mlflow.log_param("dataset_size", len(results))

        metric_keys = [
            "answer_relevancy",
            "faithfulness",
            "contextual_precision",
            "hallucination",
        ]
        for key in metric_keys:
            values = [r[key] for r in results if r.get(key) is not None]
            if values:
                avg = sum(values) / len(values)
                mlflow.log_metric(f"deepeval_{key}_mean", avg)
                mlflow.log_metric(f"deepeval_{key}_count", len(values))

        mlflow.log_dict(results, "deepeval_results.json")
        logger.info("deepeval_logged_to_mlflow", run_name=run_name, result_count=len(results))


def log_promptfoo_results(
    output_path: str,
    run_name: str = "promptfoo_sweep",
    judge_model: str | None = None,
) -> None:
    """Read promptfoo JSON/CSV output and log metrics to MLflow.

    This is the custom glue wrapper — promptfoo does NOT log to MLflow
    natively.

    Args:
        output_path: Path to promptfoo's output JSON file.
        run_name: Name for the MLflow run.
        judge_model: The Claude model configured as promptfoo's grader,
            logged as a param for reproducibility.
    """
    output_file = Path(output_path)
    if not output_file.exists():
        logger.error("promptfoo_output_not_found", path=output_path)
        return

    data = json.loads(output_file.read_text())

    with mlflow.start_run(run_name=run_name):
        _tag_common("promptfoo", judge_model)

        # Extract pass/fail rates from promptfoo output
        results = data.get("results", {})
        stats = results.get("stats", {})

        if stats:
            mlflow.log_param("dataset_size", stats.get("total", 0))
            mlflow.log_metric("promptfoo_pass_rate", stats.get("passRate", 0))
            mlflow.log_metric("promptfoo_total_tests", stats.get("total", 0))
            mlflow.log_metric("promptfoo_passed", stats.get("passed", 0))
            mlflow.log_metric("promptfoo_failed", stats.get("failed", 0))

        # Log raw output as artifact
        mlflow.log_artifact(output_path, "promptfoo")
        logger.info("promptfoo_logged_to_mlflow", run_name=run_name)


def main() -> None:
    """CLI entrypoint for the promptfoo Job step.

    RAGAS/DeepEval call log_*_results() directly from their own scripts'
    _main() and never need this CLI — this exists solely because promptfoo
    is a separate `npx` process with no Python entrypoint of its own to
    call log_promptfoo_results() from.
    """
    parser = argparse.ArgumentParser(description="Log promptfoo results to MLflow.")
    parser.add_argument(
        "--promptfoo-output", type=str, required=True, help="Path to promptfoo's output JSON."
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default="claude-haiku-4-5",
        help="Claude model configured as promptfoo's grader (see promptfooconfig.yaml).",
    )
    args = parser.parse_args()

    mlflow_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
    init_mlflow(mlflow_uri)
    log_promptfoo_results(args.promptfoo_output, judge_model=args.judge_model)


if __name__ == "__main__":
    main()
