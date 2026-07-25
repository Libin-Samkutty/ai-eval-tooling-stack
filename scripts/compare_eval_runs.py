#!/usr/bin/env python3
"""Compare the two most recent MLflow eval runs for a metric.

Wires src/eval/stats.py (scipy/statsmodels confidence intervals and
significance testing, PLAN.md §9) into a live entrypoint: pulls the per-item
metric values logged as an artifact by the two most recent runs of a given
framework and reports whether the change between them is statistically
significant, not just a raw pass-rate delta.

No Vertex AI calls — reads only from MLflow's already-logged runs/artifacts.
"""

from __future__ import annotations

import argparse
import json
import os

import mlflow
import structlog
from mlflow.tracking import MlflowClient

from src.eval.stats import compare_runs

logger = structlog.get_logger(__name__)

FRAMEWORK_ARTIFACTS = {
    "ragas": ("ragas_results.json", ["context_precision", "faithfulness", "answer_relevancy"]),
    "deepeval": (
        "deepeval_results.json",
        ["answer_relevancy", "faithfulness", "contextual_precision", "hallucination"],
    ),
}


def _load_metric_values(
    client: MlflowClient, run_id: str, artifact_file: str, metric: str
) -> list[float]:
    local_path = mlflow.artifacts.download_artifacts(
        run_id=run_id, artifact_path=artifact_file, tracking_uri=client.tracking_uri
    )
    with open(local_path) as f:
        data = json.load(f)
    return [r[metric] for r in data["results"] if r.get(metric) is not None]


def compare_latest_runs(
    framework: str, metric: str, experiment_name: str, tracking_uri: str
) -> None:
    """Compare the two most recent runs of `framework` on `metric`."""
    if framework not in FRAMEWORK_ARTIFACTS:
        raise ValueError(f"framework must be one of {list(FRAMEWORK_ARTIFACTS)}, got {framework!r}")
    artifact_file, valid_metrics = FRAMEWORK_ARTIFACTS[framework]
    if metric not in valid_metrics:
        raise ValueError(f"metric for {framework!r} must be one of {valid_metrics}, got {metric!r}")

    mlflow.set_tracking_uri(tracking_uri)
    client = MlflowClient(tracking_uri=tracking_uri)

    experiment = client.get_experiment_by_name(experiment_name)
    if experiment is None:
        logger.error("experiment_not_found", experiment=experiment_name)
        return

    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        filter_string=f"tags.framework = '{framework}'",
        order_by=["start_time DESC"],
        max_results=2,
    )
    if len(runs) < 2:
        logger.error(
            "not_enough_runs",
            framework=framework,
            found=len(runs),
            needed=2,
        )
        return

    newer_run, older_run = runs[0], runs[1]
    older_values = _load_metric_values(client, older_run.info.run_id, artifact_file, metric)
    newer_values = _load_metric_values(client, newer_run.info.run_id, artifact_file, metric)

    result = compare_runs(older_values, newer_values, metric)

    logger.info(
        "eval_run_comparison",
        framework=framework,
        metric=metric,
        older_run=older_run.info.run_id,
        newer_run=newer_run.info.run_id,
        run_a_mean=result.run_a_mean,
        run_b_mean=result.run_b_mean,
        mean_difference=result.mean_difference,
        ci=[result.ci_lower, result.ci_upper],
        p_value=result.p_value,
        significant=result.significant,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework", required=True, choices=list(FRAMEWORK_ARTIFACTS))
    parser.add_argument("--metric", required=True, help="e.g. faithfulness, answer_relevancy")
    parser.add_argument("--experiment", default="oss-ai-eval-stack")
    parser.add_argument(
        "--tracking-uri", default=os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
    )
    args = parser.parse_args()

    compare_latest_runs(args.framework, args.metric, args.experiment, args.tracking_uri)


if __name__ == "__main__":
    main()
