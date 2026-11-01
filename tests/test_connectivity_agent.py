import json
import pandas as pd
import pytest

from agents.connectivity_agent import (
    ConnectivityAgent,
    ConnectivityAgentResponse,
    ConnectivityFinding,
    ConnectivitySeverity,
    ConnectivityStatus,
    ConnectivityThresholds,
)
from communication.models import AgentMessage, AgentStatus, Severity
from communication.protocol import validate_message
from communication.telemetry_schema import DNSStatus, DHCPStatus, TelemetryRecord


# ---------------------------------------------------------------------------
# BASELINE TESTS (Preserved from Milestone 1)
# ---------------------------------------------------------------------------

def test_connectivity_agent_nominal():
    agent = ConnectivityAgent()
    df = pd.DataFrame([
        {
            "device_id": "endpoint-1",
            "dns_resolution_status": "success",
            "dns_latency_ms": 12.0,
            "dhcp_status": "bound",
            "wifi_rssi_dbm": -55.0,
            "wifi_snr_db": 30.0,
            "connectivity_status": "connected",
        }
    ])
    msg = agent.execute("TASK-C1", df)
    assert msg.status == AgentStatus.SUCCESS
    assert "Healthy Connectivity" in msg.findings[0].title
    assert msg.overall_status == "healthy"


def test_connectivity_agent_dns_and_dhcp_failure():
    agent = ConnectivityAgent()
    df = pd.DataFrame([
        {
            "device_id": "endpoint-1",
            "dns_resolution_status": "servfail",
            "dns_latency_ms": 450.0,
            "dhcp_status": "exhausted",
            "wifi_rssi_dbm": -88.0,
            "wifi_snr_db": 10.0,
            "connectivity_status": "disconnected",
        }
    ])
    msg = agent.execute("TASK-C2", df)
    assert msg.status == AgentStatus.SUCCESS
    titles = [f.title for f in msg.findings]
    assert any("DNS Resolution Failure" in t for t in titles)
    assert any("DHCP Pool Exhaustion" in t for t in titles)
    assert any("Weak Wi-Fi" in t for t in titles)
    assert msg.overall_status == "critical"


# ---------------------------------------------------------------------------
# MILESTONE 5 TESTS: DNS ANOMALIES
# ---------------------------------------------------------------------------

def test_connectivity_agent_dns_failure():
    agent = ConnectivityAgent()
    telemetry = [
        {"device_id": "laptop-01", "dns_status": "failed"}
    ]
    resp = agent.analyze_telemetry(telemetry, task_id="TASK-DNS-FAIL")
    assert resp.overall_status == "critical"
    dns_findings = [f for f in resp.findings if f.metric == "dns_status"]
    assert len(dns_findings) == 1
    assert dns_findings[0].severity == "critical"
    assert "failed" in dns_findings[0].observed_value.lower()
    assert "DNS Resolution Failure" in dns_findings[0].title


def test_connectivity_agent_high_dns_latency():
    agent = ConnectivityAgent()

    # Warning: 180ms (>100ms and <=300ms)
    warn_resp = agent.analyze_telemetry([
        {"device_id": "laptop-02", "dns_latency_ms": 180.0}
    ])
    assert warn_resp.overall_status == "degraded"
    warn_f = [f for f in warn_resp.findings if f.metric == "dns_latency_ms"][0]
    assert warn_f.severity == "warning"
    assert "Degraded DNS" in warn_f.title

    # Critical: 350ms (>300ms)
    crit_resp = agent.analyze_telemetry([
        {"device_id": "laptop-02", "dns_latency_ms": 350.0}
    ])
    assert crit_resp.overall_status == "critical"
    crit_f = [f for f in crit_resp.findings if f.metric == "dns_latency_ms"][0]
    assert crit_f.severity == "critical"
    assert "Critical DNS Query Delay" in crit_f.title


# ---------------------------------------------------------------------------
# MILESTONE 5 TESTS: DHCP ANOMALIES
# ---------------------------------------------------------------------------

def test_connectivity_agent_dhcp_failure():
    agent = ConnectivityAgent()
    telemetry = [
        {"device_id": "pos-terminal-01", "dhcp_status": "failed"}
    ]
    resp = agent.analyze_telemetry(telemetry)
    assert resp.overall_status == "critical"
    dhcp_findings = [f for f in resp.findings if f.metric == "dhcp_status"]
    assert len(dhcp_findings) == 1
    assert dhcp_findings[0].severity == "critical"
    assert "Allocation Failure" in dhcp_findings[0].title


def test_connectivity_agent_dhcp_timeout():
    agent = ConnectivityAgent()
    telemetry = [
        {"device_id": "pos-terminal-02", "dhcp_status": "timeout"}
    ]
    resp = agent.analyze_telemetry(telemetry)
    assert resp.overall_status == "critical"
    dhcp_findings = [f for f in resp.findings if f.metric == "dhcp_status"]
    assert len(dhcp_findings) == 1
    assert dhcp_findings[0].severity == "critical"
    assert "timeout" in dhcp_findings[0].observed_value.lower()


# ---------------------------------------------------------------------------
# MILESTONE 5 TESTS: WI-FI RF ANOMALIES
# ---------------------------------------------------------------------------

def test_connectivity_agent_weak_wifi_signal():
    agent = ConnectivityAgent()
    # RSSI -68 dBm (below -60 dBm warning threshold, above -75 dBm critical)
    telemetry = [
        {"device_id": "mobile-client-01", "wifi_rssi_dbm": -68.0}
    ]
    resp = agent.analyze_telemetry(telemetry)
    assert resp.overall_status == "degraded"
    wifi_f = [f for f in resp.findings if f.metric == "wifi_signal_dbm"][0]
    assert wifi_f.severity == "warning"
    assert "Degraded Wi-Fi" in wifi_f.title


def test_connectivity_agent_critical_wifi_signal():
    agent = ConnectivityAgent()
    # RSSI -82 dBm (below -75 dBm critical threshold)
    telemetry = [
        {"device_id": "mobile-client-02", "wifi_signal_dbm": -82.0}
    ]
    resp = agent.analyze_telemetry(telemetry)
    assert resp.overall_status == "critical"
    wifi_f = [f for f in resp.findings if f.metric == "wifi_signal_dbm"][0]
    assert wifi_f.severity == "critical"
    assert "Weak Wi-Fi" in wifi_f.title


# ---------------------------------------------------------------------------
# MILESTONE 5 TESTS: INTERFACE & LINK DISCONNECTION
# ---------------------------------------------------------------------------

def test_connectivity_agent_interface_down():
    agent = ConnectivityAgent()
    telemetry = [
        {"device_id": "workstation-05", "interface_status": "down"}
    ]
    resp = agent.analyze_telemetry(telemetry)
    assert resp.overall_status == "critical"
    link_f = [f for f in resp.findings if f.metric == "link_status"][0]
    assert link_f.severity == "critical"
    assert "Disconnected" in link_f.title


# ---------------------------------------------------------------------------
# MILESTONE 5 TESTS: COMPOSITE CORRELATION REASONING
# ---------------------------------------------------------------------------

def test_connectivity_agent_multiple_simultaneous_connectivity_problems():
    agent = ConnectivityAgent()
    # Triggers DNS failure + high latency composite degradation, and Weak Wi-Fi with loss
    telemetry = [
        {
            "device_id": "branch-endpoint-1",
            "dns_status": "servfail",
            "dns_latency_ms": 320.0,
            "dhcp_status": "bound",
            "wifi_rssi_dbm": -78.0,
            "packet_loss_percent": 12.0,
        }
    ]
    resp = agent.analyze_telemetry(telemetry)
    assert resp.overall_status == "critical"
    metrics = [f.metric for f in resp.findings]
    assert "dns_status" in metrics
    assert "dns_latency_ms" in metrics
    assert "composite_dns_degradation" in metrics
    assert "composite_wireless_degradation" in metrics

    dns_comp = [f for f in resp.findings if f.metric == "composite_dns_degradation"][0]
    assert dns_comp.severity == "critical"
    assert "DNS Service Degradation" in dns_comp.title


# ---------------------------------------------------------------------------
# MILESTONE 5 TESTS: MULTI-DEVICE ANALYSIS
# ---------------------------------------------------------------------------

def test_connectivity_agent_multi_device_analysis():
    agent = ConnectivityAgent()
    telemetry = [
        {"device_id": "dev-healthy", "dns_status": "success", "dhcp_status": "bound", "wifi_rssi_dbm": -52.0},
        {"device_id": "dev-warning", "dns_status": "success", "dhcp_status": "bound", "wifi_rssi_dbm": -67.0},
        {"device_id": "dev-critical", "dns_status": "timeout", "dhcp_status": "timeout", "wifi_rssi_dbm": -85.0},
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
# MILESTONE 5 TESTS: MISSING METRICS & RESILIENCE
# ---------------------------------------------------------------------------

def test_connectivity_agent_missing_optional_metrics():
    agent = ConnectivityAgent()
    # Device has only device_id and dns_status
    telemetry = [{"device_id": "minimal-dev", "dns_status": "success"}]
    resp = agent.analyze_telemetry(telemetry)
    assert resp.overall_status == "healthy"
    assert resp.analyzed_device_count == 1
    assert len(resp.errors) == 0


def test_connectivity_agent_invalid_record_isolation():
    agent = ConnectivityAgent()
    telemetry = [
        {"dns_status": "success"},  # Missing device_id -> should be isolated
        {"device_id": "bad-rssi-dev", "wifi_rssi_dbm": -150.0},  # Below -120 dBm bound
        {"device_id": "good-dev", "dns_status": "success", "wifi_rssi_dbm": -54.0},  # Valid
    ]
    resp = agent.analyze_telemetry(telemetry)
    assert resp.analyzed_device_count == 1
    assert "good-dev" in resp.device_summaries
    assert len(resp.errors) >= 2  # Error descriptions for bad records
    assert resp.overall_status == "healthy"


def test_connectivity_agent_empty_telemetry():
    agent = ConnectivityAgent()
    resp = agent.analyze_telemetry([])
    assert resp.overall_status == "insufficient_data"
    assert resp.analyzed_device_count == 0
    assert resp.confidence == 0.0


# ---------------------------------------------------------------------------
# MILESTONE 5 TESTS: CONFIGURABLE THRESHOLDS
# ---------------------------------------------------------------------------

def test_connectivity_agent_configurable_thresholds():
    custom_thresholds = ConnectivityThresholds(
        dns_latency_warn_ms=50.0,
        dns_latency_crit_ms=120.0,
        wifi_rssi_warn_dbm=-55.0,
    )
    agent = ConnectivityAgent(thresholds=custom_thresholds)

    # 70ms DNS latency is warning under custom 50ms threshold (normal under default 100ms)
    telemetry = [{"device_id": "strict-dev", "dns_latency_ms": 70.0}]
    resp = agent.analyze_telemetry(telemetry)
    assert resp.overall_status == "degraded"
    finding = resp.findings[0]
    assert finding.severity == "warning"
    assert finding.observed_value == 70.0


# ---------------------------------------------------------------------------
# MILESTONE 5 TESTS: SCHEMA VALIDATION & JSON SERIALIZATION
# ---------------------------------------------------------------------------

def test_connectivity_agent_response_schema_validation():
    agent = ConnectivityAgent()
    telemetry = [
        {"device_id": "client-schema", "dns_status": "servfail", "wifi_rssi_dbm": -82.0}
    ]
    resp = agent.analyze_telemetry(telemetry, task_id="TASK-CONN-SCHEMA")
    assert isinstance(resp, ConnectivityAgentResponse)

    dumped = resp.model_dump()
    assert dumped["agent_id"] == "connectivity_agent"
    assert dumped["task_id"] == "TASK-CONN-SCHEMA"
    assert dumped["overall_status"] == "critical"
    assert isinstance(dumped["findings"], list)
    assert isinstance(dumped["device_summaries"], dict)

    # Validate JSON serialization
    json_str = resp.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["agent_id"] == "connectivity_agent"
    assert len(parsed["findings"]) >= 2


def test_connectivity_agent_orchestrator_compatibility():
    agent = ConnectivityAgent()
    telemetry = [
        {"device_id": "client-orch", "dns_status": "timeout", "dhcp_status": "exhausted"}
    ]
    resp = agent.execute("TASK-CONN-ORCH", telemetry)

    # 1. Verify to_agent_message works
    agent_msg = resp.to_agent_message()
    assert isinstance(agent_msg, AgentMessage)
    assert agent_msg.status == AgentStatus.SUCCESS
    assert agent_msg.agent_id == "connectivity_agent"
    assert len(agent_msg.findings) >= 2

    # 2. Verify validate_message handles ConnectivityAgentResponse transparently
    validated = validate_message(resp)
    assert isinstance(validated, AgentMessage)
    assert validated.agent_id == "connectivity_agent"
    assert len(validated.findings) >= 2
