from __future__ import annotations

from datetime import datetime, timezone
import pytest
from agents.baseline_detector import BaselineDetector, BaselineAnomaly
from evaluation.generator_hard import HardTelemetryDatasetGenerator
from orchestrator.orchestrator import CentralOrchestrator


def test_warmup_period_handled():
    """Verify that during the initial warmup window (first 10 samples), no anomalies are raised."""
    detector = BaselineDetector(alpha=0.1, z_threshold=3.0, sustained_required=2, warmup_period=10)

    for i in range(10):
        val = 100.0 if i < 8 else 500.0
        res = detector.update("router-1", "latency_ms", val)
        assert res is None, f"Expected no anomaly during warmup period at sample {i+1}"
        anomalies = detector.score("router-1", "latency_ms", val)
        assert len(anomalies) == 0


def test_stable_signal_not_flagged():
    """Verify that a stable telemetry signal hovering around normal does not trigger any anomaly."""
    detector = BaselineDetector(alpha=0.05, z_threshold=3.5, sustained_required=3, warmup_period=10)

    # 30 stable samples around 24ms with small normal variance
    import random
    rng = random.Random(42)
    for _ in range(30):
        val = 24.0 + rng.gauss(0, 0.2)
        detector.update("core-switch-1", "rtt_ms", val)
        anomalies = detector.score("core-switch-1", "rtt_ms", val)
        assert len(anomalies) == 0, f"False positive triggered for stable signal at value {val:.2f}"

    state = detector.get_state("core-switch-1", "rtt_ms")
    assert state is not None
    assert state["sustained_points"] == 0


def test_sudden_isolated_spike_not_flagged():
    """Verify that a single isolated spike (|z| > 3.5 for 1 sample) does NOT trigger without sustained counts."""
    detector = BaselineDetector(alpha=0.05, min_std=0.5, z_threshold=3.5, sustained_required=3, warmup_period=10)

    for _ in range(15):
        detector.update("switch-core", "rtt_ms", 20.0)

    # Isolated single spike
    spike_res = detector.update("switch-core", "rtt_ms", 150.0)
    assert spike_res is None, "Isolated spike should not trigger sustained alarm"

    # Return to normal
    normal_res = detector.update("switch-core", "rtt_ms", 20.0)
    assert normal_res is None

    # Check that sustained count was reset
    state = detector.get_state("switch-core", "rtt_ms")
    assert state is not None
    assert state["sustained_points"] == 0


def test_gradual_silent_drift_detected_before_static_threshold():
    """
    Demonstrate that gradual silent degradation (e.g. latency drifting from 15ms to 32ms)
    triggers an anomaly via BaselineDetector well before crossing a traditional static threshold of 50ms.
    """
    STATIC_THRESHOLD = 50.0
    detector = BaselineDetector(alpha=0.03, min_std=0.5, z_threshold=3.5, sustained_required=3, warmup_period=15)

    import random
    rng = random.Random(42)
    for _ in range(25):
        detector.update("ap-floor2", "latency_ms", 15.0 + rng.gauss(0, 0.2))

    triggered_anomaly: BaselineAnomaly | None = None
    max_val_at_trigger = 0.0

    current_latency = 15.0
    for step in range(40):
        current_latency += 0.5
        anomaly = detector.update("ap-floor2", "latency_ms", current_latency)
        if anomaly and triggered_anomaly is None:
            triggered_anomaly = anomaly
            max_val_at_trigger = current_latency
            break

    assert triggered_anomaly is not None, "BaselineDetector failed to catch silent degradation drift"
    assert max_val_at_trigger < STATIC_THRESHOLD, (
        f"Anomaly was triggered at {max_val_at_trigger:.2f}ms, which should be strictly below "
        f"the static threshold of {STATIC_THRESHOLD}ms"
    )
    assert triggered_anomaly["sustained_points"] >= 3
    assert abs(triggered_anomaly["z_score"]) > 3.5
    assert "rolling baseline" in triggered_anomaly["description"]


def test_missing_metrics_handled_cleanly():
    """Verify that None/NaN missing telemetry values do not reset or break the detector state."""
    detector = BaselineDetector(alpha=0.05, z_threshold=3.0, sustained_required=2, warmup_period=10)

    for _ in range(15):
        detector.update("srv-db", "cpu_utilization_pct", 25.0)

    state_before = detector.get_state("srv-db", "cpu_utilization_pct")
    assert state_before is not None
    count_before = state_before["count"]

    # Missing samples
    detector.update("srv-db", "cpu_utilization_pct", None)
    detector.update("srv-db", "cpu_utilization_pct", float("nan"))

    state_after = detector.get_state("srv-db", "cpu_utilization_pct")
    assert state_after is not None
    assert state_after["count"] == count_before
    assert abs(state_after["mean"] - state_before["mean"]) < 1e-6


def test_record_dictionary_update_and_score():
    """Verify that update(record) and score(record) work with full telemetry dictionaries."""
    detector = BaselineDetector(alpha=0.05, min_std=0.5, z_threshold=3.5, sustained_required=3, warmup_period=10)

    for i in range(12):
        rec = {
            "device_id": "core-router-01",
            "latency_ms": 20.0,
            "packet_loss_pct": 0.0,
            "cpu_utilization_pct": 30.0,
        }
        detector.update(rec)
        assert len(detector.score(rec)) == 0

    # Inject sustained latency drift
    anomalies = []
    for i in range(5):
        rec = {
            "device_id": "core-router-01",
            "latency_ms": 35.0,  # +15ms drift
            "packet_loss_pct": 0.0,
            "cpu_utilization_pct": 30.0,
        }
        anoms = detector.update_and_score(rec)
        if anoms:
            anomalies.extend(anoms)

    assert len(anomalies) > 0
    first = anomalies[0]
    assert first["device_id"] == "core-router-01"
    assert first["metric"] == "latency_ms"
    assert first["direction"] == "above"
    assert "sigma above this device's rolling baseline" in first["description"]


def test_orchestrator_toggleable_and_silent_drift_scenario():
    """
    Verify requirement 4 & 5:
    In 'silent_drift' scenario (RTT drifts +15% over time, never crossing 150ms):
    - enable_baseline=False: rules alone report NOMINAL (health HEALTHY, certainty NOT_APPLICABLE).
    - enable_baseline=True: detector catches silent degradation, yielding DEGRADED / PROVISIONAL.
    """
    gen = HardTelemetryDatasetGenerator(seed=7)
    records, affected, rc, desc = gen._generate_silent_drift_episode(
        "ep-test-drift", 0, datetime.now(timezone.utc)
    )

    # 1. With enable_baseline=False: rules alone report NOMINAL
    orch_off = CentralOrchestrator(enable_baseline=False)
    rep_off = orch_off.run_diagnosis(records, save_report=False)
    assert rep_off.overall_network_health.value == "HEALTHY"
    assert rep_off.diagnosis_certainty == "NOT_APPLICABLE"
    assert not rep_off.fault_detected
    assert "Nominal" in rep_off.probable_root_cause.title

    # 2. With enable_baseline=True: detector catches drift, yields DEGRADED / PROVISIONAL
    orch_on = CentralOrchestrator(enable_baseline=True)
    rep_on = orch_on.run_diagnosis(records, save_report=False)
    assert rep_on.overall_network_health.value == "DEGRADED"
    assert rep_on.diagnosis_certainty == "PROVISIONAL"
    assert rep_on.fault_detected
    assert "Silent Performance Degradation" in rep_on.probable_root_cause.title
    assert len(rep_on.supporting_evidence) > 0
    assert any("rolling baseline" in e.details for e in rep_on.supporting_evidence if e.details)
