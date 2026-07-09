"""Statistical rigor — confidence intervals and significance testing.

Uses scipy and statsmodels to analyze MLflow-logged eval runs. No
additional API calls — this runs against logged metrics only.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import structlog
from pydantic import BaseModel
from scipy import stats

logger = structlog.get_logger(__name__)


class MetricComparison(BaseModel):
    """Comparison of a metric across two eval runs."""

    metric_name: str
    run_a_mean: float
    run_b_mean: float
    mean_difference: float
    ci_lower: float
    ci_upper: float
    p_value: float
    significant: bool


def compare_runs(
    run_a_values: list[float],
    run_b_values: list[float],
    metric_name: str,
    confidence_level: float = 0.95,
) -> MetricComparison:
    """Compare a metric between two eval runs with statistical rigor.

    Uses Welch's t-test (does not assume equal variances) and computes
    a confidence interval for the mean difference.

    Args:
        run_a_values: Metric values from run A (e.g., previous cycle).
        run_b_values: Metric values from run B (e.g., current cycle).
        metric_name: Name of the metric being compared.
        confidence_level: Confidence level for the interval (default 0.95).

    Returns:
        MetricComparison with the difference, CI, and significance.
    """
    a = np.array(run_a_values)
    b = np.array(run_b_values)

    mean_diff = float(np.mean(b) - np.mean(a))

    # Welch's t-test
    _t_stat, p_value = stats.ttest_ind(b, a, equal_var=False)

    # Confidence interval for the difference (Welch-Satterthwaite df, matching
    # the equal_var=False assumption used for the t-test above)
    var_a_over_n = np.var(a, ddof=1) / len(a)
    var_b_over_n = np.var(b, ddof=1) / len(b)
    se = np.sqrt(var_a_over_n + var_b_over_n)
    df = (var_a_over_n + var_b_over_n) ** 2 / (
        var_a_over_n**2 / (len(a) - 1) + var_b_over_n**2 / (len(b) - 1)
    )
    t_crit = stats.t.ppf((1 + confidence_level) / 2, df=df)
    ci_lower = mean_diff - t_crit * se
    ci_upper = mean_diff + t_crit * se

    alpha = 1 - confidence_level
    result = MetricComparison(
        metric_name=metric_name,
        run_a_mean=float(np.mean(a)),
        run_b_mean=float(np.mean(b)),
        mean_difference=mean_diff,
        ci_lower=float(ci_lower),
        ci_upper=float(ci_upper),
        p_value=float(p_value),
        significant=bool(p_value < alpha),
    )

    logger.info(
        "run_comparison",
        metric=metric_name,
        mean_diff=f"{mean_diff:.4f}",
        ci=f"[{ci_lower:.4f}, {ci_upper:.4f}]",
        p_value=f"{p_value:.4f}",
        significant=result.significant,
    )

    return result


def compute_confidence_interval(
    values: list[float],
    metric_name: str,
    confidence_level: float = 0.95,
) -> dict[str, Any]:
    """Compute a confidence interval for a single run's metric.

    Args:
        values: Metric values from a single eval run.
        metric_name: Name of the metric.
        confidence_level: Confidence level (default 0.95).

    Returns:
        Dict with mean, CI bounds, and standard error.
    """
    arr = np.array(values)
    mean = float(np.mean(arr))
    se = float(stats.sem(arr))
    ci = stats.t.interval(confidence_level, df=len(arr) - 1, loc=mean, scale=se)

    result = {
        "metric": metric_name,
        "mean": mean,
        "ci_lower": float(ci[0]),
        "ci_upper": float(ci[1]),
        "se": se,
        "n": len(values),
    }

    logger.info(
        "confidence_interval",
        metric=metric_name,
        mean=f"{mean:.4f}",
        ci=f"[{ci[0]:.4f}, {ci[1]:.4f}]",
        n=len(values),
    )

    return result
