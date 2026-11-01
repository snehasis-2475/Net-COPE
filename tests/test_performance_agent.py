from __future__ import annotations

from datetime import datetime, timezone
import pandas as pd
import pytest

from app.agents.performance_agent import (
    PerformanceAgent,
    PerformanceAgentResponse,
    PerformanceFinding,
    PerformanceSeverity,
    PerformanceStatus,
    PerformanceThresholds,
)
from communication.models import AgentStatus
from communication.telemetry_generator import TelemetryGenerator
from communication.telemetry_schema import TelemetryRecord


# ============================================================================
# 1. NOMINAL TELEMETRY TESTS
# ============================================================================

def test_performance_agent_nominal():
    agent = PerformanceAgent()
    df = pd.DataFrame([
        {"device_id": "r1", "latency_ms": 12.0, "jitter_ms": 1.5, "packet_loss_percent": 0.0, "bandwidth_utilization_percent": 35.0},
        {"device_id": "r1", "latency_ms": 14.0, "jitter_ms": 2.0, "packet_loss_percent": 0.0, "bandwidth_utilization_percent": 40.0},
    ])
    msg = agent.execute("TASK-P1", df)
    assert msg.overall_performance_status == PerformanceStatus.HEALTHY.value
    assert msg.execution_status == "SUCCESS"
    assert msg.status == AgentStatus.SUCCESS
    assert msg.confidence >= 0.70
    assert len(msg.analyzed_device_ids) == 1
    assert "r1" in msg.analyzed_device_ids
    assert len(msg.findings) == 1
    assert "nominal" in msg.findings[0].observed_value or "Nominal" in msg.findings[0].description


# ============================================================================
# 2. INDIVIDUAL METRIC ANOMALY TESTS
# ============================================================================

def test_performance_agent_high_latency_warning_and_critical():
    agent = PerformanceAgent()

    # Warning latency (> 50ms, <= 150ms)
    df_warn = pd.DataFrame([
        {"device_id": "r1", "latency_ms": 85.0},
        {"device_id": "r1", "latency_ms": 95.0},
    ])
    res_warn = agent.analyze_telemetry(df_warn)
    assert res_warn.overall_performance_status == PerformanceStatus.DEGRADED.value
    lat_findings_warn = [f for f in res_warn.findings if f.metric_name == "latency_ms"]
    assert len(lat_findings_warn) > 0
    assert lat_findings_warn[0].severity in ["medium", "high"]
    assert "implication" in lat_findings_warn[0].probable_implication.lower() or len(lat_findings_warn[0].probable_implication) > 0

    # Critical latency (> 150ms)
    df_crit = pd.DataFrame([
        {"device_id": "r1", "latency_ms": 190.0},
        {"device_id": "r1", "latency_ms": 210.0},
    ])
    res_crit = agent.analyze_telemetry(df_crit)
    assert res_crit.overall_performance_status == PerformanceStatus.CRITICAL.value
    lat_findings_crit = [f for f in res_crit.findings if f.metric_name == "latency_ms"]
    assert len(lat_findings_crit) > 0
    assert lat_findings_crit[0].severity == "critical"
    assert lat_findings_crit[0].observed_value >= 190.0
    assert lat_findings_crit[0].expected_range == "<= 50.0 ms"


def test_performance_agent_high_jitter():
    agent = PerformanceAgent()

    # Jitter > 50ms critical
    df = pd.DataFrame([
        {"device_id": "sw1", "jitter_ms": 65.0},
    ])
    res = agent.analyze_telemetry(df)
    assert res.overall_performance_status == PerformanceStatus.CRITICAL.value
    jitter_finding = [f for f in res.findings if f.metric_name == "jitter_ms"][0]
    assert jitter_finding.severity == "critical"
    assert jitter_finding.observed_value == 65.0
    assert "packet reordering" in jitter_finding.probable_implication.lower() or "audio" in jitter_finding.probable_implication.lower()


def test_performance_agent_high_packet_loss():
    agent = PerformanceAgent()

    # Packet loss > 5% critical
    df = pd.DataFrame([
        {"device_id": "sw1", "packet_loss_percent": 8.5},
    ])
    res = agent.analyze_telemetry(df)
    assert res.overall_performance_status == PerformanceStatus.CRITICAL.value
    loss_finding = [f for f in res.findings if f.metric_name == "packet_loss_percent"][0]
    assert loss_finding.severity == "critical"
    assert loss_finding.observed_value == 8.5
    assert "retransmission" in loss_finding.probable_implication.lower()


def test_performance_agent_high_bandwidth_utilization():
    agent = PerformanceAgent()

    # Bandwidth > 90% critical
    df = pd.DataFrame([
        {"device_id": "core-01", "bandwidth_utilization_percent": 96.0},
    ])
    res = agent.analyze_telemetry(df)
    assert res.overall_performance_status == PerformanceStatus.CRITICAL.value
    bw_finding = [f for f in res.findings if f.metric_name == "bandwidth_utilization_percent"][0]
    assert bw_finding.severity == "critical"
    assert bw_finding.observed_value == 96.0
    assert "buffer" in bw_finding.probable_implication.lower() or "capacity" in bw_finding.probable_implication.lower()


# ============================================================================
# 3. MULTIPLE SIMULTANEOUS ANOMALIES
# ============================================================================

def test_performance_agent_multiple_simultaneous_anomalies():
    agent = PerformanceAgent()
    df = pd.DataFrame([
        {
            "device_id": "core-01",
            "latency_ms": 185.0,
            "jitter_ms": 55.0,
            "packet_loss_percent": 9.0,
            "bandwidth_utilization_percent": 95.0,
        }
    ])
    res = agent.analyze_telemetry(df)
    assert res.overall_performance_status == PerformanceStatus.CRITICAL.value
    assert len(res.findings) >= 4
    metrics_detected = {f.metric_name for f in res.findings}
    assert "latency_ms" in metrics_detected
    assert "jitter_ms" in metrics_detected
    assert "packet_loss_percent" in metrics_detected
    assert "bandwidth_utilization_percent" in metrics_detected


# ============================================================================
# 4. THROUGHPUT WITH CONFIGURED EXPECTED THROUGHPUT
# ============================================================================

def test_performance_agent_low_throughput_configured_baseline():
    # Configure expected throughput of 1000 Mbps
    thresholds = PerformanceThresholds(expected_throughput_mbps=1000.0, low_throughput_ratio_threshold=0.30)
    agent = PerformanceAgent(thresholds=thresholds)

    # Throughput 150 Mbps (< 30% of 1000 Mbps)
    df = pd.DataFrame([
        {"device_id": "core-01", "throughput_mbps": 150.0},
    ])
    res = agent.analyze_telemetry(df)
    tp_findings = [f for f in res.findings if f.metric_name == "throughput_mbps"]
    assert len(tp_findings) == 1
    assert tp_findings[0].observed_value == 150.0
    # Must explicitly state that low throughput alone does not prove network fault
    assert "does not prove" in tp_findings[0].probable_implication.lower()

    # Without configured baseline, normal throughput should not flag low throughput
    agent_no_baseline = PerformanceAgent()
    res_no_base = agent_no_baseline.analyze_telemetry(df)
    tp_no_base = [f for f in res_no_base.findings if f.metric_name == "throughput_mbps"]
    assert len(tp_no_base) == 0


# ============================================================================
# 5. CONFIGURABLE THRESHOLDS TEST
# ============================================================================

def test_performance_agent_configurable_thresholds():
    # Default latency warning is > 50 ms. 40 ms should be normal.
    agent_default = PerformanceAgent()
    df = pd.DataFrame([{"device_id": "r1", "latency_ms": 40.0}])
    res_def = agent_default.analyze_telemetry(df)
    assert res_def.overall_performance_status == PerformanceStatus.HEALTHY.value

    # Custom thresholds with strict latency warning > 30 ms
    strict_thresholds = PerformanceThresholds(latency_normal_max_ms=30.0, latency_critical_ms=60.0)
    agent_strict = PerformanceAgent(thresholds=strict_thresholds)
    res_strict = agent_strict.analyze_telemetry(df)
    # 40 ms is now an anomaly under strict thresholds
    assert res_strict.overall_performance_status == PerformanceStatus.DEGRADED.value
    assert any(f.metric_name == "latency_ms" for f in res_strict.findings)


# ============================================================================
# 6. MISSING OPTIONAL METRICS
# ============================================================================

def test_performance_agent_missing_optional_metrics():
    agent = PerformanceAgent()
    # Record has only device_id and latency_ms; jitter, loss, bw are None
    data = [{"device_id": "r1", "latency_ms": 25.0}]
    res = agent.analyze_telemetry(data)
    assert res.overall_performance_status == PerformanceStatus.HEALTHY.value
    assert res.confidence >= 0.60
    assert len(res.errors) == 0


# ============================================================================
# 7. MULTI-DEVICE ANALYSIS
# ============================================================================

def test_performance_agent_multi_device_analysis():
    agent = PerformanceAgent()
    telemetry = [
        # Core router is healthy
        {"device_id": "core-router-01", "latency_ms": 12.0, "packet_loss_percent": 0.0},
        {"device_id": "core-router-01", "latency_ms": 14.0, "packet_loss_percent": 0.0},
        # Branch switch has severe packet loss
        {"device_id": "branch-switch-02", "latency_ms": 16.0, "packet_loss_percent": 8.0},
        {"device_id": "branch-switch-02", "latency_ms": 18.0, "packet_loss_percent": 10.0},
    ]
    res = agent.analyze_telemetry(telemetry)
    assert len(res.analyzed_device_ids) == 2
    assert "core-router-01" in res.analyzed_device_ids
    assert "branch-switch-02" in res.analyzed_device_ids

    # Finding should explicitly isolate to branch-switch-02
    loss_findings = [f for f in res.findings if f.metric_name == "packet_loss_percent"]
    assert len(loss_findings) > 0
    assert loss_findings[0].device_id == "branch-switch-02"


# ============================================================================
# 8. INVALID TELEMETRY HANDLING & FAILURE ISOLATION
# ============================================================================

def test_performance_agent_invalid_records_handling():
    agent = PerformanceAgent()
    mixed_data = [
        # 1. Valid record
        {"device_id": "r1", "latency_ms": 15.0, "packet_loss_percent": 0.0},
        # 2. Invalid record (negative latency)
        {"device_id": "r2", "latency_ms": -100.0},
        # 3. Invalid record (missing device_id)
        {"device_id": "", "latency_ms": 20.0},
        # 4. Valid record (high latency anomaly)
        {"device_id": "r3", "latency_ms": 180.0, "packet_loss_percent": 0.0},
    ]
    res = agent.analyze_telemetry(mixed_data)

    # Valid records r1 and r3 must be analyzed
    assert "r1" in res.analyzed_device_ids
    assert "r3" in res.analyzed_device_ids
    assert len(res.analyzed_device_ids) == 2

    # Invalid records must be captured in errors list without crashing
    assert len(res.errors) >= 2
    assert any("latency_ms cannot be negative" in e or "-100" in e for e in res.errors)
    assert any("device_id" in e for e in res.errors)

    # Finding from valid record r3 must still be produced
    assert any(f.device_id == "r3" and f.metric_name == "latency_ms" for f in res.findings)


def test_performance_agent_empty_data():
    agent = PerformanceAgent()
    res = agent.execute("TASK-EMPTY", pd.DataFrame())
    assert res.overall_performance_status == PerformanceStatus.INSUFFICIENT_DATA.value
    assert res.confidence == 0.0
    assert res.execution_status == "INSUFFICIENT_DATA"


# ============================================================================
# 9. CONFIDENCE SCORE BOUNDARIES
# ============================================================================

def test_performance_agent_confidence_boundaries():
    agent = PerformanceAgent()

    # Zero records -> confidence 0.0
    res_empty = agent.analyze_telemetry([])
    assert res_empty.confidence == 0.0

    # Many records with clear severe anomaly -> high confidence
    df_severe = pd.DataFrame([
        {"device_id": "r1", "latency_ms": 200.0, "packet_loss_percent": 15.0}
        for _ in range(12)
    ])
    res_severe = agent.analyze_telemetry(df_severe)
    assert 0.85 <= res_severe.confidence <= 1.0


# ============================================================================
# 10. SCHEMA VALIDATION AND INTEROPERABILITY
# ============================================================================

def test_performance_agent_response_schema_validation():
    agent = PerformanceAgent()
    data = [{"device_id": "r1", "latency_ms": 190.0, "packet_loss_percent": 8.0}]
    res = agent.analyze_telemetry(data, task_id="TASK-SCHEMA-1")

    # Verify Pydantic serialization
    dumped_dict = res.model_dump()
    assert dumped_dict["agent_id"] == "performance_agent"
    assert dumped_dict["task_id"] == "TASK-SCHEMA-1"
    assert dumped_dict["overall_performance_status"] == "critical"
    assert isinstance(dumped_dict["findings"], list)
    assert len(dumped_dict["findings"]) >= 2

    # Verify JSON export
    json_str = res.model_dump_json()
    assert "latency_ms" in json_str

    # Verify adaptation to global AgentMessage
    agent_msg = res.to_agent_message()
    assert agent_msg.agent_id == "performance_agent"
    assert agent_msg.status == AgentStatus.SUCCESS
    assert len(agent_msg.findings) >= 2


# ============================================================================
# 11. TESTING WITH SYNTHETIC SCENARIOS GENERATOR
# ============================================================================

def test_performance_agent_with_synthetic_scenarios():
    agent = PerformanceAgent()

    # Normal scenario
    normal_records = TelemetryGenerator.generate("normal", count=10)
    res_normal = agent.analyze_telemetry(normal_records)
    assert res_normal.overall_performance_status == PerformanceStatus.HEALTHY.value
    assert res_normal.confidence >= 0.80

    # Congestion scenario
    congestion_records = TelemetryGenerator.generate("congestion", count=12)
    res_congestion = agent.analyze_telemetry(congestion_records)
    assert res_congestion.overall_performance_status in [PerformanceStatus.DEGRADED.value, PerformanceStatus.CRITICAL.value]
    detected_metrics = {f.metric_name for f in res_congestion.findings}
    assert "bandwidth_utilization_percent" in detected_metrics or "latency_ms" in detected_metrics
