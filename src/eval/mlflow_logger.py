"""MLflow logging wrapper — bridges eval tool outputs to MLflow.

promptfoo outputs JSON/CSV natively. This module reads those outputs
and logs them as MLflow metrics. This is NOT automatic — it's a custom
glue layer.

Also used by RAGAS and DeepEval eval scripts to log their results.
"""

from __future__ import annotations

import json
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


def log_ragas_results(results: list[dict[str, Any]], run_name: str = "ragas_sweep") -> None:
    """Log RAGAS evaluation results to MLflow.

    Args:
        results: List of result dicts with metric values.
        run_name: Name for the MLflow run.
    """
    with mlflow.start_run(run_name=run_name):
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


def log_deepeval_results(results: list[dict[str, Any]], run_name: str = "deepeval_sweep") -> None:
    """Log DeepEval evaluation results to MLflow.

    Args:
        results: List of result dicts with metric values.
        run_name: Name for the MLflow run.
    """
    with mlflow.start_run(run_name=run_name):
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


def log_promptfoo_results(output_path: str, run_name: str = "promptfoo_sweep") -> None:
    """Read promptfoo JSON/CSV output and log metrics to MLflow.

    This is the custom glue wrapper — promptfoo does NOT log to MLflow
    natively.

    Args:
        output_path: Path to promptfoo's output JSON file.
        run_name: Name for the MLflow run.
    """
    output_file = Path(output_path)
    if not output_file.exists():
        logger.error("promptfoo_output_not_found", path=output_path)
        return

    data = json.loads(output_file.read_text())

    with mlflow.start_run(run_name=run_name):
        # Extract pass/fail rates from promptfoo output
        results = data.get("results", {})
        stats = results.get("stats", {})

        if stats:
            mlflow.log_metric("promptfoo_pass_rate", stats.get("passRate", 0))
            mlflow.log_metric("promptfoo_total_tests", stats.get("total", 0))
            mlflow.log_metric("promptfoo_passed", stats.get("passed", 0))
            mlflow.log_metric("promptfoo_failed", stats.get("failed", 0))

        # Log raw output as artifact
        mlflow.log_artifact(output_path, "promptfoo")
        logger.info("promptfoo_logged_to_mlflow", run_name=run_name)
