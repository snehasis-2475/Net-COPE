import json
from pathlib import Path
import pytest

from communication.telemetry_schema import TelemetryRecord
from evaluation.generator import TelemetryDatasetGenerator
from evaluation.metrics import (
    ConfidenceMetrics,
    EvaluationSummary,
    FaultDetectionMetrics,
    RecommendationSafetyMetrics,
    RobustnessMetrics,
    RootCauseMetrics,
    calculate_metrics,
)
from evaluation.evaluate import EvaluationRunner


# ---------------------------------------------------------------------------
# 1. DATASET GENERATION & REPRODUCIBILITY
# ---------------------------------------------------------------------------

def test_dataset_reproducibility():
    """Verify that using the same seed produces bit-identical dataset records."""
    gen1 = TelemetryDatasetGenerator(seed=123)
    recs1, labels1, meta1 = gen1.generate_dataset(episodes_per_scenario=2)

    gen2 = TelemetryDatasetGenerator(seed=123)
    recs2, labels2, meta2 = gen2.generate_dataset(episodes_per_scenario=2)

    assert len(recs1) == len(recs2)
    assert recs1 == recs2
    assert labels1 == labels2
    assert meta1["total_records"] == meta2["total_records"]


def test_dataset_minimum_record_count_and_scenario_classes():
    """Verify minimum 1,000 records and all 8 scenario classes are represented."""
    gen = TelemetryDatasetGenerator(seed=42)
    recs, labels, meta = gen.generate_dataset(episodes_per_scenario=12)

    assert len(recs) >= 1000
    assert meta["total_records"] >= 1000
    assert len(labels) == 96  # 12 * 8 scenarios

    scenario_classes = meta["scenario_classes"]
    expected_scenarios = [
        "normal",
        "congestion",
        "weak_wifi",
        "interface_failure",
        "dns_failure",
        "dhcp_failure",
        "infrastructure_overload",
        "invalid_telemetry",
    ]
    for sc in expected_scenarios:
        assert sc in scenario_classes
        assert meta["scenario_distribution"][sc] == 12


def test_ground_truth_separation_no_data_leakage():
    """CRITICAL: Telemetry records must NEVER contain ground truth labels."""
    gen = TelemetryDatasetGenerator(seed=42)
    recs, labels, _ = gen.generate_dataset(episodes_per_scenario=2)

    forbidden_keys = {
        "ground_truth_root_cause",
        "scenario_name",
        "expected_severity",
        "is_fault",
        "is_robustness_test",
        "split",
    }

    for rec in recs:
        # episode_id is permitted for grouping in evaluation harness, but labels must never be present
        for key in forbidden_keys:
            assert key not in rec, f"Data leakage detected! Telemetry record contained ground truth key: {key}"


def test_dataset_schema_validity():
    """Verify that standard (non-invalid) records parse cleanly through TelemetryRecord schema."""
    gen = TelemetryDatasetGenerator(seed=42)
    recs, labels, _ = gen.generate_dataset(episodes_per_scenario=2)

    valid_episodes = {ep_id for ep_id, l in labels.items() if l["scenario_name"] != "invalid_telemetry"}
    valid_recs = [r for r in recs if r["episode_id"] in valid_episodes]

    for r in valid_recs[:100]:  # Sample test first 100
        clean_r = {k: v for k, v in r.items() if k != "episode_id"}
        record = TelemetryRecord.model_validate(clean_r)
        assert record.device_id
        assert record.timestamp


# ---------------------------------------------------------------------------
# 2. SPLIT ISOLATION & BALANCED DISTRIBUTION
# ---------------------------------------------------------------------------

def test_split_isolation_by_episode():
    """Verify records from the same episode never leak across multiple splits."""
    gen = TelemetryDatasetGenerator(seed=42)
    _, labels, meta = gen.generate_dataset(episodes_per_scenario=6)

    dev_eps = {ep_id for ep_id, l in labels.items() if l["split"] == "dev"}
    val_eps = {ep_id for ep_id, l in labels.items() if l["split"] == "val"}
    test_eps = {ep_id for ep_id, l in labels.items() if l["split"] == "test"}

    # Set disjointness
    assert len(dev_eps.intersection(val_eps)) == 0
    assert len(dev_eps.intersection(test_eps)) == 0
    assert len(val_eps.intersection(test_eps)) == 0


def test_balanced_scenario_distribution_across_splits():
    """Verify all scenarios are represented in each split."""
    gen = TelemetryDatasetGenerator(seed=42)
    _, labels, _ = gen.generate_dataset(episodes_per_scenario=12)

    for split in ["dev", "val", "test"]:
        split_labels = [l for l in labels.values() if l["split"] == split]
        scenarios_in_split = {l["scenario_name"] for l in split_labels}
        assert len(scenarios_in_split) == 8, f"Split {split} is missing scenario classes!"


# ---------------------------------------------------------------------------
# 3. EVALUATION METRIC MATHEMATICAL CORRECTNESS
# ---------------------------------------------------------------------------

def test_metric_calculation_small_synthetic_example():
    """Test metric calculation with a hand-verified truth matrix."""
    classes = ["normal", "congestion", "dns_failure"]

    # 4 episodes:
    # 1: normal -> pred: normal (TP for normal, TN for fault)
    # 2: congestion -> pred: congestion (TP for congestion, TP for fault)
    # 3: dns_failure -> pred: dns_failure (TP for dns, TP for fault)
    # 4: congestion -> pred: normal (FN for congestion, FN for fault, FP for normal)
    eval_records = [
        {"actual_scenario": "normal", "predicted_scenario": "normal", "is_correct": True, "confidence": 0.95, "recommendations": []},
        {"actual_scenario": "congestion", "predicted_scenario": "congestion", "is_correct": True, "confidence": 0.90, "recommendations": []},
        {"actual_scenario": "dns_failure", "predicted_scenario": "dns_failure", "is_correct": True, "confidence": 0.85, "recommendations": []},
        {"actual_scenario": "congestion", "predicted_scenario": "normal", "is_correct": False, "confidence": 0.70, "recommendations": []},
    ]

    summary = calculate_metrics(
        eval_records=eval_records,
        robustness_records=[],
        scenario_classes=classes,
        split_name="test_small",
    )

    rc = summary.root_cause_metrics
    fd = summary.fault_detection_metrics

    # Overall accuracy: 3/4 = 75%
    assert rc.accuracy == 0.75
    assert rc.total_evaluated == 4
    assert rc.correct_count == 3

    # Binary fault detection:
    # Actual faults: items 2, 3, 4 (3 items)
    # Predicted faults: items 2, 3 (2 items) -> TP = 2, FN = 1
    # Actual normal: item 1 (1 item)
    # Predicted normal on item 1 -> TN = 1; predicted normal on item 4 -> FP = 0 (FP is when normal network flagged as fault)
    assert fd.true_positives == 2
    assert fd.false_negatives == 1
    assert fd.true_negatives == 1
    assert fd.false_positives == 0
    assert fd.false_positive_rate == 0.0


def test_confusion_matrix_correctness():
    """Verify confusion matrix cells match exact pair frequencies."""
    classes = ["normal", "congestion", "weak_wifi"]
    eval_records = [
        {"actual_scenario": "normal", "predicted_scenario": "normal", "is_correct": True, "confidence": 0.9, "recommendations": []},
        {"actual_scenario": "congestion", "predicted_scenario": "weak_wifi", "is_correct": False, "confidence": 0.8, "recommendations": []},
        {"actual_scenario": "weak_wifi", "predicted_scenario": "weak_wifi", "is_correct": True, "confidence": 0.9, "recommendations": []},
    ]

    summary = calculate_metrics(eval_records, [], classes, "matrix_test")
    cm = summary.root_cause_metrics.confusion_matrix

    assert cm["normal"]["normal"] == 1
    assert cm["congestion"]["weak_wifi"] == 1
    assert cm["weak_wifi"]["weak_wifi"] == 1
    assert cm["congestion"]["congestion"] == 0


# ---------------------------------------------------------------------------
# 4. ROBUSTNESS & SAFETY SAFEGUARDS
# ---------------------------------------------------------------------------

def test_robustness_metrics_isolation():
    """Verify invalid telemetry is evaluated separately from root cause accuracy."""
    classes = ["normal", "congestion"]
    eval_recs = [
        {"actual_scenario": "normal", "predicted_scenario": "normal", "is_correct": True, "confidence": 0.95, "recommendations": []},
    ]
    rob_recs = [
        {"actual_scenario": "invalid_telemetry", "predicted_root_cause": "Invalid or Empty Telemetry", "execution_status": "FAILED", "errors": ["corrupt timestamp"], "recommendations": []},
    ]

    summary = calculate_metrics(eval_recs, rob_recs, classes, "rob_test")
    assert summary.root_cause_metrics.total_evaluated == 1  # invalid_telemetry not counted in root cause accuracy
    assert summary.robustness_metrics.total_robustness_episodes == 1
    assert summary.robustness_metrics.graceful_handling_rate == 1.0
    assert summary.robustness_metrics.zero_disruptive_actions_on_invalid is True


def test_recommendation_safety_approval_metrics():
    """Verify that disruptive actions without human approval trigger safety metric drop."""
    classes = ["normal"]
    eval_recs = [
        {
            "actual_scenario": "normal",
            "predicted_scenario": "normal",
            "is_correct": True,
            "confidence": 0.9,
            "recommendations": [
                {"title": "Restart Core Switch", "execution_risk": "high", "requires_human_approval": True, "rollback_steps": ["revert"], "supporting_evidence": ["log"]},
                {"title": "Query Latency", "execution_risk": "low", "requires_human_approval": False, "rollback_steps": [], "supporting_evidence": ["ping"]},
            ],
        }
    ]

    summary = calculate_metrics(eval_recs, [], classes, "safety_test")
    rs = summary.recommendation_safety
    assert rs.total_recommendations == 2
    assert rs.disruptive_actions_count == 1
    assert rs.disruptive_approval_rate == 1.0
    assert rs.low_risk_no_approval_rate == 1.0


# ---------------------------------------------------------------------------
# 5. END-TO-END EVALUATION RUNNER & REPORT GENERATION
# ---------------------------------------------------------------------------

def test_evaluation_runner_small_split(tmp_path):
    """Verify end-to-end evaluation runner executes and saves reports."""
    dataset_dir = tmp_path / "data"
    reports_dir = tmp_path / "reports"

    # Generate small 2-episode dataset
    gen = TelemetryDatasetGenerator(seed=42)
    gen.save_dataset(output_dir=dataset_dir, episodes_per_scenario=2)

    runner = EvaluationRunner(dataset_dir=dataset_dir, reports_dir=reports_dir, seed=42)
    summary = runner.run_evaluation(split="test", save_reports=True)

    assert isinstance(summary, EvaluationSummary)
    assert summary.total_episodes > 0
    assert (reports_dir / "evaluation_summary.json").exists()
    assert (reports_dir / "confusion_matrix.json").exists()
    assert (reports_dir / "evaluation_report.md").exists()

    # Verify JSON content
    with open(reports_dir / "evaluation_summary.json", "r", encoding="utf-8") as f:
        data = json.load(f)
        assert "root_cause_metrics" in data
        assert "fault_detection_metrics" in data

    # Verify Markdown formatting
    with open(reports_dir / "evaluation_report.md", "r", encoding="utf-8") as f:
        md_text = f.read()
        assert "# NetCoop AI Evaluation Report" in md_text
        assert "Confusion Matrix" in md_text
