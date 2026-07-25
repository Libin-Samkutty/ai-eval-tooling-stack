"""Tests for evaluation modules."""

from __future__ import annotations

import json

# ── Golden dataset loading ────────────────────────────


def test_load_golden_dataset(tmp_path):
    """Golden dataset loads correctly with limit."""
    from src.eval.ragas_eval import load_golden_dataset

    dataset = [
        {
            "id": "q001",
            "question": "What is RAG?",
            "ground_truth_contexts": ["RAG is..."],
            "reference_answer": "RAG combines retrieval and generation.",
            "metadata": {"topic": "rag", "difficulty": "easy"},
        },
        {
            "id": "q002",
            "question": "What is MLflow?",
            "ground_truth_contexts": ["MLflow is..."],
            "reference_answer": "MLflow tracks experiments.",
            "metadata": {"topic": "tracking", "difficulty": "easy"},
        },
    ]

    path = tmp_path / "golden.json"
    path.write_text(json.dumps(dataset))

    items = load_golden_dataset(str(path), limit=1)
    assert len(items) == 1
    assert items[0].id == "q001"

    items = load_golden_dataset(str(path), limit=10)
    assert len(items) == 2


# ── Statistical rigor ─────────────────────────────────


def test_compare_runs():
    """compare_runs produces valid statistical comparison."""
    from src.eval.stats import compare_runs

    run_a = [0.7, 0.75, 0.72, 0.68, 0.71, 0.74, 0.69, 0.73, 0.70, 0.72]
    run_b = [0.8, 0.82, 0.79, 0.81, 0.83, 0.78, 0.80, 0.82, 0.81, 0.79]

    result = compare_runs(run_a, run_b, "faithfulness")
    assert result.metric_name == "faithfulness"
    assert result.run_a_mean < result.run_b_mean
    assert result.ci_lower < result.ci_upper
    assert isinstance(result.significant, bool)


def test_confidence_interval():
    """compute_confidence_interval produces valid interval."""
    from src.eval.stats import compute_confidence_interval

    values = [0.7, 0.75, 0.72, 0.68, 0.71, 0.74, 0.69, 0.73, 0.70, 0.72]
    result = compute_confidence_interval(values, "faithfulness")

    assert result["metric"] == "faithfulness"
    assert result["ci_lower"] < result["mean"] < result["ci_upper"]
    assert result["n"] == 10


# ── Red team ──────────────────────────────────────────


def test_xpia_scenarios_defined():
    """Default XPIA scenarios are properly defined."""
    from src.redteam.pyrit_xpia import DEFAULT_SCENARIOS

    assert len(DEFAULT_SCENARIOS) == 2
    for scenario in DEFAULT_SCENARIOS:
        assert scenario.name
        assert scenario.poisoned_chunk
        assert scenario.trigger_query
        assert scenario.expected_behavior
        assert scenario.max_turns <= 5


def test_garak_default_probes():
    """Default Garak probes list has 10 entries."""
    from src.redteam.garak_probe import DEFAULT_PROBES

    assert len(DEFAULT_PROBES) == 10


def test_fairness_audit_items():
    """Example audit items are balanced across groups."""
    from src.redteam.fairlearn_audit import EXAMPLE_AUDIT_ITEMS

    assert len(EXAMPLE_AUDIT_ITEMS) == 10
    groups = {item.group for item in EXAMPLE_AUDIT_ITEMS}
    assert len(groups) == 5  # 5 groups x 2 items each
