import json
import pandas as pd
import pytest

from agents.infrastructure_agent import (
    InfrastructureAgent,
    InfrastructureAgentResponse,
    InfrastructureFinding,
    InfrastructureSeverity,
    InfrastructureStatus,
    InfrastructureThresholds,
)
from communication.models import AgentMessage, AgentStatus, Severity
from communication.protocol import validate_message
from communication.telemetry_schema import DeviceStatus, TelemetryRecord


# ---------------------------------------------------------------------------
# BASELINE TESTS (Preserved from Milestone 1)
# ---------------------------------------------------------------------------

def test_infrastructure_agent_nominal():
    agent = InfrastructureAgent()
    df = pd.DataFrame([
        {
            "device_id": "sw1",
            "device_availability": 100.0,
            "cpu_util_pct": 25.0,
            "memory_util_pct": 40.0,
            "interface_status": "up",
            "interface_errors": 0,
            "queue_drops": 0,
        },
    ])
    msg = agent.execute("TASK-I1", df)
    assert msg.status == AgentStatus.SUCCESS
    assert "Healthy Infrastructure Status" in msg.findings[0].title
    assert msg.overall_status == "healthy"


def test_infrastructure_agent_cpu_and_interface_flapping():
    agent = InfrastructureAgent()
    df = pd.DataFrame([
        {
            "device_id": "sw1",
            "device_availability": 60.0,
            "cpu_util_pct": 95.0,
            "memory_util_pct": 92.0,
            "interface_status": "flapping",
            "interface_errors": 180,
            "queue_drops": 45,
        },
    ])
    msg = agent.execute("TASK-I2", df)
    assert msg.status == AgentStatus.SUCCESS
    assert len(msg.evidence) >= 4

    titles = [f.title for f in msg.findings]
    assert any("CPU Overload" in t for t in titles)
    assert any("Interface Physical" in t for t in titles)
    assert any("CRC Errors" in t for t in titles)
    assert msg.overall_status == "critical"


# ---------------------------------------------------------------------------
# MILESTONE 4 TESTS: CPU ANOMALIES
# ---------------------------------------------------------------------------

def test_infrastructure_agent_high_cpu_warning():
    agent = InfrastructureAgent()
    telemetry = [
        {"device_id": "core-router-01", "cpu_utilization_percent": 78.5, "memory_utilization_percent": 50.0}
    ]
    resp = agent.analyze_telemetry(telemetry, task_id="TASK-CPU-WARN")
    assert resp.overall_status == "degraded"
    assert len(resp.findings) == 1
    finding = resp.findings[0]
    assert finding.metric == "cpu_utilization"
    assert finding.severity == "warning"
    assert finding.observed_value == 78.5
    assert finding.confidence >= 0.80
    assert "High CPU Warning" in finding.title


def test_infrastructure_agent_critical_cpu():
    agent = InfrastructureAgent()
    telemetry = [
        {"device_id": "dist-switch-02", "cpu_util_pct": 94.0, "memory_util_pct": 60.0}
    ]
    resp = agent.execute("TASK-CPU-CRIT", telemetry)
    assert resp.overall_status == "critical"
    crit_findings = [f for f in resp.findings if f.severity == "critical"]
    assert len(crit_findings) >= 1
    assert crit_findings[0].metric == "cpu_utilization"
    assert crit_findings[0].observed_value == 94.0
    assert crit_findings[0].confidence >= 0.85
    assert "Critical CPU Overload" in crit_findings[0].title


# ---------------------------------------------------------------------------
# MILESTONE 4 TESTS: MEMORY ANOMALIES
# ---------------------------------------------------------------------------

def test_infrastructure_agent_memory_warning_and_critical():
    agent = InfrastructureAgent()

    # Warning: 82% (>75% warning, <=90% critical)
    warn_resp = agent.analyze_telemetry([
        {"device_id": "agg-sw-1", "cpu_util_pct": 30.0, "memory_util_pct": 82.0}
    ])
    assert warn_resp.overall_status == "degraded"
    warn_findings = [f for f in warn_resp.findings if f.metric == "memory_utilization"]
    assert len(warn_findings) == 1
    assert warn_findings[0].severity == "warning"

    # Critical: 95% (>90% critical)
    crit_resp = agent.analyze_telemetry([
        {"device_id": "agg-sw-1", "cpu_util_pct": 30.0, "memory_util_pct": 95.0}
    ])
    assert crit_resp.overall_status == "critical"
    crit_findings = [f for f in crit_resp.findings if f.metric == "memory_utilization"]
    assert len(crit_findings) == 1
    assert crit_findings[0].severity == "critical"
    assert "Memory Pressure" in crit_findings[0].title


# ---------------------------------------------------------------------------
# MILESTONE 4 TESTS: DEVICE OPERATIONAL STATUS
# ---------------------------------------------------------------------------

def test_infrastructure_agent_device_offline_and_degraded():
    agent = InfrastructureAgent()

    # Degraded state
    deg_resp = agent.analyze_telemetry([
        {"device_id": "edge-ap-12", "device_status": "degraded"}
    ])
    assert deg_resp.overall_status == "degraded"
    deg_finding = [f for f in deg_resp.findings if f.metric == "device_status"][0]
    assert deg_finding.severity == "warning"
    assert "Degraded" in deg_finding.title

    # Offline state
    off_resp = agent.analyze_telemetry([
        {"device_id": "edge-ap-12", "device_status": "offline"}
    ])
    assert off_resp.overall_status == "critical"
    off_finding = [f for f in off_resp.findings if f.metric == "device_status"][0]
    assert off_finding.severity == "critical"
    assert "Offline" in off_finding.title


# ---------------------------------------------------------------------------
# MILESTONE 4 TESTS: INTERFACE ERRORS & QUEUE DROPS
# ---------------------------------------------------------------------------

def test_infrastructure_agent_interface_errors_warning_and_critical():
    agent = InfrastructureAgent()

    # Warning: 5 errors (>0 and <=20)
    warn_resp = agent.analyze_telemetry([
        {"device_id": "core-sw-01", "interface_errors": 5}
    ])
    assert warn_resp.overall_status == "degraded"
    warn_f = [f for f in warn_resp.findings if f.metric == "interface_errors"][0]
    assert warn_f.severity == "warning"
    assert "cumulative" in warn_f.evidence.lower()

    # Critical: 35 errors (>20)
    crit_resp = agent.analyze_telemetry([
        {"device_id": "core-sw-01", "interface_errors": 35}
    ])
    assert crit_resp.overall_status == "critical"
    crit_f = [f for f in crit_resp.findings if f.metric == "interface_errors"][0]
    assert crit_f.severity == "critical"
    assert "cumulative" in crit_f.evidence.lower()


def test_infrastructure_agent_queue_drops_warning_and_critical():
    agent = InfrastructureAgent()

    # Warning: 15 drops (>0 and <=50)
    warn_resp = agent.analyze_telemetry([
        {"device_id": "gw-router-01", "queue_drops": 15}
    ])
    assert warn_resp.overall_status == "degraded"
    warn_f = [f for f in warn_resp.findings if f.metric == "queue_drops"][0]
    assert warn_f.severity == "warning"

    # Critical: 80 drops (>50)
    crit_resp = agent.analyze_telemetry([
        {"device_id": "gw-router-01", "queue_drops": 80}
    ])
    assert crit_resp.overall_status == "critical"
    crit_f = [f for f in crit_resp.findings if f.metric == "queue_drops"][0]
    assert crit_f.severity == "critical"


# ---------------------------------------------------------------------------
# MILESTONE 4 TESTS: MULTI-METRIC COMPOSITE REASONING
# ---------------------------------------------------------------------------

def test_infrastructure_agent_multiple_simultaneous_anomalies():
    agent = InfrastructureAgent()
    # High CPU (92%) + High Queue Drops (60) => triggers individual + composite hardware overload
    telemetry = [
        {
            "device_id": "core-sw-01",
            "cpu_util_pct": 92.0,
            "memory_util_pct": 65.0,
            "queue_drops": 60,
            "interface_errors": 0,
        }
    ]
    resp = agent.analyze_telemetry(telemetry)
    assert resp.overall_status == "critical"
    metrics = [f.metric for f in resp.findings]
    assert "cpu_utilization" in metrics
    assert "queue_drops" in metrics
    assert "composite_hardware_overload" in metrics

    comp_finding = [f for f in resp.findings if f.metric == "composite_hardware_overload"][0]
    assert comp_finding.severity == "critical"
    assert "Buffer Saturation" in comp_finding.title


def test_infrastructure_agent_composite_resource_exhaustion():
    agent = InfrastructureAgent()
    # High Memory (91%) + Degraded status => triggers composite resource exhaustion
    telemetry = [
        {
            "device_id": "edge-router-02",
            "cpu_util_pct": 45.0,
            "memory_util_pct": 91.0,
            "device_status": "degraded",
        }
    ]
    resp = agent.analyze_telemetry(telemetry)
    assert resp.overall_status == "critical"
    comp_finding = [f for f in resp.findings if f.metric == "composite_resource_exhaustion"][0]
    assert comp_finding.severity == "critical"
    assert "Memory Exhaustion" in comp_finding.title


# ---------------------------------------------------------------------------
# MILESTONE 4 TESTS: MULTI-DEVICE ANALYSIS
# ---------------------------------------------------------------------------

def test_infrastructure_agent_multi_device_analysis():
    agent = InfrastructureAgent()
    telemetry = [
        {"device_id": "dev-healthy", "cpu_util_pct": 20.0, "memory_util_pct": 30.0, "interface_errors": 0, "queue_drops": 0},
        {"device_id": "dev-warning", "cpu_util_pct": 75.0, "memory_util_pct": 40.0, "interface_errors": 0, "queue_drops": 0},
        {"device_id": "dev-critical", "cpu_util_pct": 95.0, "memory_util_pct": 92.0, "interface_errors": 50, "queue_drops": 60},
    ]
    resp = agent.analyze_telemetry(telemetry)
    assert resp.analyzed_device_count == 3
    assert resp.overall_status == "critical"

    # Verify per-device summaries exist
    assert "dev-healthy" in resp.device_summaries
    assert resp.device_summaries["dev-healthy"]["status"] == "healthy"

    assert "dev-warning" in resp.device_summaries
    assert resp.device_summaries["dev-warning"]["status"] == "degraded"

    assert "dev-critical" in resp.device_summaries
    assert resp.device_summaries["dev-critical"]["status"] == "critical"


# ---------------------------------------------------------------------------
# MILESTONE 4 TESTS: MISSING METRICS & RESILIENCE
# ---------------------------------------------------------------------------

def test_infrastructure_agent_missing_optional_metrics():
    agent = InfrastructureAgent()
    # Record has only device_id and cpu
    telemetry = [{"device_id": "minimal-dev", "cpu_util_pct": 40.0}]
    resp = agent.analyze_telemetry(telemetry)
    assert resp.overall_status == "healthy"
    assert resp.analyzed_device_count == 1
    assert len(resp.errors) == 0


def test_infrastructure_agent_invalid_telemetry_isolation():
    agent = InfrastructureAgent()
    telemetry = [
        {"cpu_util_pct": 50.0},  # Missing device_id -> should be isolated
        {"device_id": "dev-bad-cpu", "cpu_util_pct": -15.0},  # Invalid negative CPU
        {"device_id": "dev-good", "cpu_util_pct": 45.0, "memory_util_pct": 50.0},  # Valid
    ]
    resp = agent.analyze_telemetry(telemetry)
    assert resp.analyzed_device_count == 1
    assert "dev-good" in resp.device_summaries
    assert len(resp.errors) >= 2  # Reported errors for bad records
    assert resp.overall_status == "healthy"


def test_infrastructure_agent_empty_telemetry():
    agent = InfrastructureAgent()
    resp = agent.analyze_telemetry([])
    assert resp.overall_status == "insufficient_data"
    assert resp.analyzed_device_count == 0
    assert resp.confidence == 0.0


# ---------------------------------------------------------------------------
# MILESTONE 4 TESTS: CONFIGURABLE THRESHOLDS
# ---------------------------------------------------------------------------

def test_infrastructure_agent_configurable_thresholds():
    custom_thresholds = InfrastructureThresholds(
        cpu_warn_pct=50.0,
        cpu_crit_pct=75.0,
        interface_errors_crit=10,
    )
    agent = InfrastructureAgent(thresholds=custom_thresholds)

    telemetry = [{"device_id": "sw-strict", "cpu_util_pct": 60.0}]
    resp = agent.analyze_telemetry(telemetry)
    # 60% CPU is warning under custom threshold 50.0% (would be normal under default 70.0%)
    assert resp.overall_status == "degraded"
    finding = resp.findings[0]
    assert finding.severity == "warning"
    assert finding.observed_value == 60.0


# ---------------------------------------------------------------------------
# MILESTONE 4 TESTS: SCHEMA VALIDATION & JSON SERIALIZATION
# ---------------------------------------------------------------------------

def test_infrastructure_agent_response_schema_validation():
    agent = InfrastructureAgent()
    telemetry = [
        {"device_id": "sw-schema", "cpu_util_pct": 92.0, "interface_errors": 25}
    ]
    resp = agent.analyze_telemetry(telemetry, task_id="TASK-SCHEMA-01")
    assert isinstance(resp, InfrastructureAgentResponse)

    dumped = resp.model_dump()
    assert dumped["agent_id"] == "infrastructure_agent"
    assert dumped["task_id"] == "TASK-SCHEMA-01"
    assert dumped["overall_status"] == "critical"
    assert isinstance(dumped["findings"], list)
    assert isinstance(dumped["device_summaries"], dict)

    # Validate JSON serializability
    json_str = resp.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["agent_id"] == "infrastructure_agent"
    assert len(parsed["findings"]) >= 2


def test_infrastructure_agent_orchestrator_compatibility():
    agent = InfrastructureAgent()
    telemetry = [
        {"device_id": "sw-orch", "cpu_util_pct": 95.0, "queue_drops": 60}
    ]
    resp = agent.execute("TASK-ORCH-01", telemetry)

    # 1. Verify to_agent_message works
    agent_msg = resp.to_agent_message()
    assert isinstance(agent_msg, AgentMessage)
    assert agent_msg.status == AgentStatus.SUCCESS
    assert agent_msg.agent_id == "infrastructure_agent"
    assert len(agent_msg.findings) >= 2

    # 2. Verify validate_message handles InfrastructureAgentResponse transparently
    validated = validate_message(resp)
    assert isinstance(validated, AgentMessage)
    assert validated.agent_id == "infrastructure_agent"
    assert len(validated.findings) >= 2
