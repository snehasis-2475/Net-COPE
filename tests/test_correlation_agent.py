import json
import pytest

from communication.models import (
    AgentMessage,
    AgentStatus,
    EvidenceItem,
    Finding,
    Severity,
)
from communication.protocol import create_agent_message, create_error_message, validate_message
from diagnosis.correlation_agent import FaultCorrelationAgent
from diagnosis.models import (
    CorrelationConfig,
    CorrelationHypothesis,
    CorrelationResponse,
    NetworkHealthStatus,
    RootCauseCandidate,
)


# ---------------------------------------------------------------------------
# BASELINE TESTS (Preserved from Milestone 1)
# ---------------------------------------------------------------------------

def test_correlation_agent_nominal():
    correlator = FaultCorrelationAgent()
    perf_msg = create_agent_message("T1", "performance_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="PERFORMANCE", title="Nominal Network Performance", description="Healthy", severity=Severity.INFO)
    ])
    infra_msg = create_agent_message("T1", "infrastructure_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="INFRASTRUCTURE", title="Healthy Infrastructure Status", description="Healthy", severity=Severity.INFO)
    ])
    conn_msg = create_agent_message("T1", "connectivity_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="CONNECTIVITY", title="Healthy Connectivity & Core Services", description="Healthy", severity=Severity.INFO)
    ])

    result = correlator.correlate("T1", {
        "performance_agent": perf_msg,
        "infrastructure_agent": infra_msg,
        "connectivity_agent": conn_msg,
    })

    assert result.status == AgentStatus.SUCCESS
    assert result.confidence >= 0.95
    assert result.metadata["health_status"] == NetworkHealthStatus.HEALTHY.value
    assert "Nominal" in result.metadata["probable_root_cause"]["title"]


def test_correlation_agent_congestion():
    correlator = FaultCorrelationAgent()
    perf_msg = create_agent_message("T2", "performance_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="PERFORMANCE", title="Link Bandwidth Saturation", description="96% util", severity=Severity.CRITICAL, affected_devices=["core-01"]),
        Finding(category="PERFORMANCE", title="Significant Packet Loss Detected", description="4.5% loss", severity=Severity.HIGH, affected_devices=["core-01"]),
    ], evidence=[
        EvidenceItem(metric_name="bandwidth_util_pct", observed_value=96.0, threshold=80.0),
        EvidenceItem(metric_name="packet_loss_pct", observed_value=4.5, threshold=2.0),
    ])
    infra_msg = create_agent_message("T2", "infrastructure_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="INFRASTRUCTURE", title="Hardware Queue Drops Detected", description="120 drops", severity=Severity.HIGH, affected_devices=["core-01"])
    ], evidence=[
        EvidenceItem(metric_name="queue_drops", observed_value=120, threshold=0)
    ])

    result = correlator.correlate("T2", {
        "performance_agent": perf_msg,
        "infrastructure_agent": infra_msg,
    })

    assert result.status == AgentStatus.SUCCESS
    rc = result.metadata["probable_root_cause"]
    assert "Bandwidth Congestion" in rc["title"]
    assert rc["confidence"] >= 0.80


def test_correlation_insufficient_evidence():
    correlator = FaultCorrelationAgent()
    # No agents provided
    result = correlator.correlate("T3", {})
    assert result.status == AgentStatus.INSUFFICIENT_DATA
    assert result.confidence <= 0.20


# ---------------------------------------------------------------------------
# MILESTONE 6 TESTS: SCENARIO B - INFRASTRUCTURE OVERLOAD
# ---------------------------------------------------------------------------

def test_correlation_infrastructure_overload():
    correlator = FaultCorrelationAgent()
    infra_msg = create_agent_message("T-INFRA", "infrastructure_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="INFRASTRUCTURE", title="Critical CPU Overload", description="Pegged at 96%", severity=Severity.CRITICAL, affected_devices=["router-gw"]),
        Finding(category="INFRASTRUCTURE", title="Memory Pressure / Leak Potential", description="89% RAM", severity=Severity.HIGH, affected_devices=["router-gw"]),
    ], evidence=[
        EvidenceItem(metric_name="cpu_utilization_percent", observed_value=96.0, threshold=90.0, device_id="router-gw"),
        EvidenceItem(metric_name="memory_utilization_percent", observed_value=89.0, threshold=75.0, device_id="router-gw"),
        EvidenceItem(metric_name="queue_drops", observed_value=45, threshold=0, device_id="router-gw"),
    ])
    perf_msg = create_agent_message("T-INFRA", "performance_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="PERFORMANCE", title="Excessive Latency (RTT Degradation)", description="Elevated RTT", severity=Severity.HIGH, affected_devices=["router-gw"])
    ], evidence=[
        EvidenceItem(metric_name="latency_ms", observed_value=175.0, threshold=50.0, device_id="router-gw")
    ])

    result = correlator.correlate("T-INFRA", {
        "infrastructure_agent": infra_msg,
        "performance_agent": perf_msg,
    })

    assert result.status == AgentStatus.SUCCESS
    rc = result.metadata["probable_root_cause"]
    assert "Hardware / Compute Resource Overload" in rc["title"]
    assert rc["confidence"] >= 0.85
    assert "router-gw" in rc["affected_devices"]


# ---------------------------------------------------------------------------
# MILESTONE 6 TESTS: SCENARIO C - DNS SERVICE DEGRADATION
# ---------------------------------------------------------------------------

def test_correlation_dns_service_degradation():
    correlator = FaultCorrelationAgent()
    conn_msg = create_agent_message("T-DNS", "connectivity_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="CONNECTIVITY", title="DNS Resolution Failure / Server Outage", description="SERVFAIL on queries", severity=Severity.CRITICAL, affected_devices=["client-1", "client-2"]),
        Finding(category="CONNECTIVITY", title="Critical DNS Query Delay", description="350ms latency", severity=Severity.HIGH, affected_devices=["client-1"]),
    ], evidence=[
        EvidenceItem(metric_name="dns_status", observed_value="servfail", threshold="success"),
        EvidenceItem(metric_name="dns_latency_ms", observed_value=350.0, threshold=100.0),
    ])

    result = correlator.correlate("T-DNS", {"connectivity_agent": conn_msg})
    assert result.status == AgentStatus.SUCCESS
    rc = result.metadata["probable_root_cause"]
    assert "DNS" in rc["title"]
    assert rc["confidence"] >= 0.85
    assert "client-1" in rc["affected_devices"]


# ---------------------------------------------------------------------------
# MILESTONE 6 TESTS: SCENARIO D - WIRELESS DEGRADATION
# ---------------------------------------------------------------------------

def test_correlation_wireless_degradation():
    correlator = FaultCorrelationAgent()
    conn_msg = create_agent_message("T-WIFI", "connectivity_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="CONNECTIVITY", title="Severe Wireless Signal Attenuation (Weak Wi-Fi)", description="-84 dBm RSSI", severity=Severity.CRITICAL, affected_devices=["laptop-10"])
    ], evidence=[
        EvidenceItem(metric_name="wifi_signal_dbm", observed_value=-84.0, threshold=-60.0, device_id="laptop-10"),
        EvidenceItem(metric_name="wifi_snr_db", observed_value=11.0, threshold=18.0, device_id="laptop-10"),
    ])
    perf_msg = create_agent_message("T-WIFI", "performance_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="PERFORMANCE", title="Significant Packet Loss Detected", description="12% loss", severity=Severity.HIGH, affected_devices=["laptop-10"])
    ], evidence=[
        EvidenceItem(metric_name="packet_loss_percent", observed_value=12.0, threshold=1.0, device_id="laptop-10")
    ])

    result = correlator.correlate("T-WIFI", {
        "connectivity_agent": conn_msg,
        "performance_agent": perf_msg,
    })

    assert result.status == AgentStatus.SUCCESS
    rc = result.metadata["probable_root_cause"]
    assert "Wireless" in rc["title"] or "Wi-Fi" in rc["title"]
    assert rc["confidence"] >= 0.85
    assert "laptop-10" in rc["affected_devices"]


# ---------------------------------------------------------------------------
# MILESTONE 6 TESTS: SCENARIO E - PHYSICAL INTERFACE FAILURE
# ---------------------------------------------------------------------------

def test_correlation_physical_interface_failure():
    correlator = FaultCorrelationAgent()
    infra_msg = create_agent_message("T-IFACE", "infrastructure_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="INFRASTRUCTURE", title="Interface Physical / Link Failure", description="State down", severity=Severity.CRITICAL, affected_devices=["switch-core-01"]),
        Finding(category="INFRASTRUCTURE", title="Interface Frame / CRC Errors", description="150 CRC errors", severity=Severity.HIGH, affected_devices=["switch-core-01"]),
    ], evidence=[
        EvidenceItem(metric_name="interface_status", observed_value="down", threshold="up", device_id="switch-core-01"),
        EvidenceItem(metric_name="interface_errors", observed_value=150, threshold=0, device_id="switch-core-01"),
    ])
    conn_msg = create_agent_message("T-IFACE", "connectivity_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="CONNECTIVITY", title="Loss of Network Reachability", description="Disconnected", severity=Severity.HIGH, affected_devices=["switch-core-01"])
    ], evidence=[
        EvidenceItem(metric_name="connectivity_status", observed_value="disconnected", threshold="connected", device_id="switch-core-01")
    ])

    result = correlator.correlate("T-IFACE", {
        "infrastructure_agent": infra_msg,
        "connectivity_agent": conn_msg,
    })

    assert result.status == AgentStatus.SUCCESS
    rc = result.metadata["probable_root_cause"]
    assert "Physical Interface" in rc["title"] or "Cable Failure" in rc["title"]
    assert rc["confidence"] >= 0.85


# ---------------------------------------------------------------------------
# MILESTONE 6 TESTS: SCENARIO F - DHCP FAILURE
# ---------------------------------------------------------------------------

def test_correlation_dhcp_failure():
    correlator = FaultCorrelationAgent()
    conn_msg = create_agent_message("T-DHCP", "connectivity_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="CONNECTIVITY", title="DHCP Pool Exhaustion / Allocation Failure", description="Scope exhausted", severity=Severity.CRITICAL, affected_devices=["client-dhcp-1", "client-dhcp-2"])
    ], evidence=[
        EvidenceItem(metric_name="dhcp_status", observed_value="exhausted", threshold="bound")
    ])

    result = correlator.correlate("T-DHCP", {"connectivity_agent": conn_msg})
    assert result.status == AgentStatus.SUCCESS
    rc = result.metadata["probable_root_cause"]
    assert "DHCP" in rc["title"]
    assert rc["confidence"] >= 0.85


# ---------------------------------------------------------------------------
# MILESTONE 6 TESTS: SCENARIO G - ISOLATED / CONFLICTING / INDETERMINATE
# ---------------------------------------------------------------------------

def test_correlation_isolated_weak_symptom():
    correlator = FaultCorrelationAgent()
    # Only one weak finding without corroboration
    perf_msg = create_agent_message("T-WEAK", "performance_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="PERFORMANCE", title="Elevated Latency", description="55ms", severity=Severity.LOW, affected_devices=["dev-1"])
    ], evidence=[
        EvidenceItem(metric_name="latency_ms", observed_value=55.0, threshold=50.0)
    ])

    result = correlator.correlate("T-WEAK", {"performance_agent": perf_msg})
    assert result.status == AgentStatus.WARNING
    assert result.confidence <= 0.35
    assert "Indeterminate" in result.metadata["probable_root_cause"]["title"]


def test_correlation_conflicting_evidence_resolution():
    correlator = FaultCorrelationAgent()
    # High bandwidth saturation reported, but also pegged CPU (96%)
    perf_msg = create_agent_message("T-CONF", "performance_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="PERFORMANCE", title="Link Bandwidth Saturation", description="95%", severity=Severity.CRITICAL, affected_devices=["core-router"])
    ], evidence=[
        EvidenceItem(metric_name="bandwidth_utilization_percent", observed_value=95.0, threshold=70.0)
    ])
    infra_msg = create_agent_message("T-CONF", "infrastructure_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="INFRASTRUCTURE", title="Critical CPU Overload", description="Pegged 96%", severity=Severity.CRITICAL, affected_devices=["core-router"])
    ], evidence=[
        EvidenceItem(metric_name="cpu_utilization_percent", observed_value=96.0, threshold=90.0)
    ])

    response = correlator.analyze("T-CONF", {
        "performance_agent": perf_msg,
        "infrastructure_agent": infra_msg,
    })

    # Both compute overload and congestion are evaluated; CPU overload penalized pure bandwidth congestion
    assert response.status == AgentStatus.SUCCESS
    assert len(response.alternative_hypotheses) >= 1
    # Check that uncertainty or competing explanations are captured
    titles = [response.primary_hypothesis.title] + [alt.title for alt in response.alternative_hypotheses]
    assert any("Compute Resource Overload" in t for t in titles)
    assert any("Bandwidth Congestion" in t for t in titles)


# ---------------------------------------------------------------------------
# MILESTONE 6 TESTS: MULTI-AGENT CORROBORATION BOOST & RESILIENCE
# ---------------------------------------------------------------------------

def test_correlation_multi_agent_corroboration_boost():
    config = CorrelationConfig(multi_agent_boost=0.15)
    correlator = FaultCorrelationAgent(config=config)

    # Congestion corroborated by BOTH Performance and Infrastructure
    perf_msg = create_agent_message("T-BOOST", "performance_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="PERFORMANCE", title="Link Bandwidth Saturation", description="95%", severity=Severity.CRITICAL)
    ], evidence=[
        EvidenceItem(metric_name="bandwidth_utilization_percent", observed_value=95.0, threshold=70.0)
    ])
    infra_msg = create_agent_message("T-BOOST", "infrastructure_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="INFRASTRUCTURE", title="Hardware Queue Drops Detected", description="100 drops", severity=Severity.HIGH)
    ], evidence=[
        EvidenceItem(metric_name="queue_drops", observed_value=100, threshold=0)
    ])

    response = correlator.analyze("T-BOOST", {
        "performance_agent": perf_msg,
        "infrastructure_agent": infra_msg,
    })

    assert "performance_agent" in response.primary_hypothesis.supporting_agents
    assert "infrastructure_agent" in response.primary_hypothesis.supporting_agents
    assert response.confidence >= 0.85


def test_correlation_missing_and_errored_agent_handling():
    correlator = FaultCorrelationAgent()
    # Performance agent errored, infrastructure agent timed out, connectivity agent succeeded
    error_perf = create_error_message("T-MISS", "performance_agent", "Agent process crash")
    conn_msg = create_agent_message("T-MISS", "connectivity_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="CONNECTIVITY", title="DNS Resolution Failure / Server Outage", description="SERVFAIL", severity=Severity.CRITICAL, affected_devices=["client-1"])
    ], evidence=[
        EvidenceItem(metric_name="dns_status", observed_value="servfail", threshold="success")
    ])

    result = correlator.correlate("T-MISS", {
        "performance_agent": error_perf,
        "connectivity_agent": conn_msg,
    })

    assert result.status == AgentStatus.SUCCESS
    assert "DNS" in result.metadata["probable_root_cause"]["title"]
    assert len(result.errors) >= 1  # Processed the error message gracefully


# ---------------------------------------------------------------------------
# MILESTONE 6 TESTS: CONFIGURATION & SCHEMA VALIDATION
# ---------------------------------------------------------------------------

def test_correlation_config_customization():
    custom_cfg = CorrelationConfig(
        min_confidence_threshold=0.50,
        high_confidence_threshold=0.90,
        multi_agent_boost=0.08,
    )
    correlator = FaultCorrelationAgent(config=custom_cfg)
    assert correlator.config.min_confidence_threshold == 0.50
    assert correlator.config.high_confidence_threshold == 0.90


def test_correlation_response_and_hypothesis_schema():
    correlator = FaultCorrelationAgent()
    perf_msg = create_agent_message("T-SCH", "performance_agent", AgentStatus.SUCCESS, findings=[
        Finding(category="PERFORMANCE", title="Link Bandwidth Saturation", description="95%", severity=Severity.CRITICAL, affected_devices=["sw-core"])
    ], evidence=[
        EvidenceItem(metric_name="bandwidth_utilization_percent", observed_value=95.0, threshold=70.0, device_id="sw-core")
    ])

    response = correlator.analyze("T-SCH", {"performance_agent": perf_msg})
    assert isinstance(response, CorrelationResponse)
    assert isinstance(response.primary_hypothesis, CorrelationHypothesis)

    # Validate required hypothesis fields
    hyp = response.primary_hypothesis
    assert hyp.hypothesis_id.startswith("HYP-")
    assert hyp.probable_root_cause != ""
    assert hyp.category == "PERFORMANCE"
    assert "sw-core" in hyp.affected_devices
    assert len(hyp.supporting_findings) >= 1
    assert hyp.probable_impact != ""
    assert hyp.recommended_investigation != ""

    # Test JSON serialization
    json_str = response.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["agent_id"] == "correlation_agent"
    assert "primary_hypothesis" in parsed

    # Test conversion to AgentMessage
    agent_msg = response.to_agent_message()
    assert isinstance(agent_msg, AgentMessage)
    validated = validate_message(response)
    assert isinstance(validated, AgentMessage)
