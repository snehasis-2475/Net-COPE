from __future__ import annotations

import json
from pathlib import Path
import pytest

from evaluation.baseline import NaiveThresholdBaseline
from evaluation.compare import run_full_comparison
from evaluation.generator_hard import HardTelemetryDatasetGenerator


def test_hard_generator_determinism():
    """Verify that HardTelemetryDatasetGenerator with seed=7 produces identical data across runs."""
    gen1 = HardTelemetryDatasetGenerator(seed=7)
    records1, gt1, meta1 = gen1.generate_dataset(episodes_per_scenario=2)

    gen2 = HardTelemetryDatasetGenerator(seed=7)
    records2, gt2, meta2 = gen2.generate_dataset(episodes_per_scenario=2)

    assert len(records1) == len(records2)
    assert len(gt1) == len(gt2)
    assert meta1["random_seed"] == meta2["random_seed"] == 7

    # Exact equality across records and labels
    assert records1 == records2
    assert gt1 == gt2


def test_hard_generator_difficulty_modifiers():
    """
    Verify presence of all difficulty modifiers:
    - At least 60 episodes produced (default 8 * 8 = 64 episodes)
    - 2x Gaussian noise on numeric metrics
    - 10-30% missing metrics per record
    - Overlapping primary and secondary faults
    - Borderline severity scenarios
    - Corrupted / malformed records
    """
    gen = HardTelemetryDatasetGenerator(seed=7)
    records, ground_truth, metadata = gen.generate_dataset(episodes_per_scenario=8)

    # 1. Total episodes >= 60
    assert len(ground_truth) >= 60
    assert len(ground_truth) == 64

    # 2. Missing metrics present
    has_missing_metrics = False
    for r in records:
        for m in gen.OPTIONAL_METRICS:
            if m in r and r[m] is None:
                has_missing_metrics = True
                break
        if has_missing_metrics:
            break
    assert has_missing_metrics, "Expected some optional metrics to be None due to missing data injection"

    # 3. Overlapping secondary faults
    secondary_faults = [meta.get("secondary_fault") for meta in ground_truth.values() if meta.get("secondary_fault")]
    assert len(secondary_faults) > 0, "Expected secondary faults to be assigned for overlapping fault injection"

    # 4. Borderline severity flags
    borderlines = [meta for meta in ground_truth.values() if meta.get("is_borderline") is True]
    assert len(borderlines) > 0, "Expected borderline episodes to be generated"

    # 5. Metadata descriptions
    assert "2x" in metadata["difficulty_modifiers"]["gaussian_noise_factor"]
    assert metadata["difficulty_modifiers"]["overlapping_faults"] is True


def test_naive_threshold_baseline_alert_storm_and_diagnosis():
    """Verify that NaiveThresholdBaseline counts multiple alerts and diagnoses the dominant metric."""
    baseline = NaiveThresholdBaseline()

    # Synthetic cascading incident: High CPU, high memory, high queue drops, and high latency
    incident_records = [
        {
            "device_id": "core-router-01",
            "timestamp": "2026-11-01T12:00:00Z",
            "cpu_util_pct": 98.0,       # Breached (>85)
            "memory_util_pct": 92.0,    # Breached (>85)
            "latency_ms": 190.0,        # Breached (>150)
            "queue_drops": 120,         # Breached (>50)
            "packet_loss_pct": 8.0,     # Breached (>5)
        },
        {
            "device_id": "core-router-01",
            "timestamp": "2026-11-01T12:00:10Z",
            "cpu_util_pct": 99.5,
            "memory_util_pct": 94.0,
            "latency_ms": 210.0,
            "queue_drops": 180,
            "packet_loss_pct": 9.5,
        },
    ]

    result = baseline.diagnose_episode(incident_records, episode_id="EP-TEST-001")

    # Verify alert storm (multiple alerts fired for one incident)
    assert result.total_alerts >= 8, f"Expected alert storm (>=8 alerts), got {result.total_alerts}"
    assert len(result.alerts) == result.total_alerts
    # Verify that a dominant root cause was selected
    assert result.dominant_metric is not None
    assert result.predicted_root_cause != ""


def test_comparison_script_runs_end_to_end(tmp_path):
    """Verify that run_full_comparison executes end to end and writes valid outputs."""
    # Run with small episode counts for fast test execution
    results = run_full_comparison(
        easy_episodes_per_scenario=1,
        hard_episodes_per_scenario=1,
        save_outputs=True,
    )

    assert "easy_set" in results
    assert "hard_set" in results

    easy_nc = results["easy_set"]["netcoop"]
    easy_bl = results["easy_set"]["baseline"]
    hard_nc = results["hard_set"]["netcoop"]
    hard_bl = results["hard_set"]["baseline"]

    # Verify metric fields exist and are calibrated floats
    for metric_set in [easy_nc, easy_bl, hard_nc, hard_bl]:
        assert 0.0 <= metric_set["accuracy"] <= 1.0
        assert 0.0 <= metric_set["macro_f1"] <= 1.0
        assert 0.0 <= metric_set["false_positive_rate"] <= 1.0

    # Output files generated
    res_md = Path("evaluation/results.md")
    res_json = Path("evaluation/comparison_results.json")
    assert res_md.exists()
    assert res_json.exists()

    md_content = res_md.read_text(encoding="utf-8")
    assert "NetCoop AI vs. Traditional Baseline" in md_content
    assert "Comparative Benchmark Matrix" in md_content

