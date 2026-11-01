import json
import pytest

from communication.models import AgentMessage, AgentStatus, EvidenceItem, Finding, Severity
from communication.protocol import create_agent_message, validate_message
from diagnosis.models import (
    ActionPriority,
    ActionType,
    CorrectiveAction,
    ExecutionRisk,
    RecommendationAgentResponse,
    RecommendationItem,
    RootCauseCandidate,
)
from diagnosis.recommendation_agent import RecommendationAgent


# ---------------------------------------------------------------------------
# BASELINE TESTS (Preserved from Milestone 1)
# ---------------------------------------------------------------------------

def test_recommendation_agent_dns_actions():
    recommender = RecommendationAgent()
    rc = RootCauseCandidate(
        title="DNS Resolver Outage or Misconfiguration",
        description="DNS servers failing queries.",
        confidence=0.92,
        affected_devices=["workstation-1"],
    )
    corr_msg = create_agent_message(
        task_id="T-REC1",
        agent_id="correlation_agent",
        status=AgentStatus.SUCCESS,
        confidence=0.92,
        metadata={"probable_root_cause": rc.model_dump()},
    )

    msg = recommender.recommend("T-REC1", corr_msg)
    assert msg.status == AgentStatus.SUCCESS
    actions = msg.metadata.get("actions", [])
    assert len(actions) >= 2
    titles = [a["title"] for a in actions]
    assert any("DNS" in t for t in titles)
    assert any("Command" in str(a.get("automation_command", "")) or "powershell" in str(a.get("automation_command", "")) for a in actions)


def test_recommendation_agent_interface_actions():
    recommender = RecommendationAgent()
    rc = RootCauseCandidate(
        title="Physical Interface / Cable Failure",
        description="Interface flapping.",
        confidence=0.95,
        affected_devices=["edge-switch-01"],
    )
    corr_msg = create_agent_message(
        task_id="T-REC2",
        agent_id="correlation_agent",
        metadata={"probable_root_cause": rc.model_dump()},
    )

    msg = recommender.recommend("T-REC2", corr_msg)
    actions = msg.metadata.get("actions", [])
    assert len(actions) >= 2
    assert any("Bounce Interface" in a["title"] for a in actions)


# ---------------------------------------------------------------------------
# MILESTONE 7 TESTS: SCENARIO-SPECIFIC REMEDIATION PLANS
# ---------------------------------------------------------------------------

def test_recommendations_network_congestion():
    recommender = RecommendationAgent()
    rc = RootCauseCandidate(
        title="Network Bandwidth Congestion & Bufferbloat",
        description="Interface bandwidth saturated.",
        confidence=0.95,
        affected_devices=["core-router-01"],
    )
    corr_msg = create_agent_message("T-CONGEST", "correlation_agent", metadata={"probable_root_cause": rc.model_dump()})

    response = recommender.generate_recommendations("T-CONGEST", corr_msg)
    assert response.status == AgentStatus.SUCCESS
    assert len(response.recommendations) >= 3

    titles = [r.title for r in response.recommendations]
    # Check required elements: top talkers, QoS shaping, capacity expansion
    assert any("Top-Talker" in t for t in titles)
    assert any("Traffic Shaping" in t or "QoS" in t for t in titles)
    assert any("Capacity" in t or "Aggregation" in t for t in titles)

    # First action must be read-only diagnostic
    assert response.recommendations[0].execution_risk == ExecutionRisk.LOW.value
    assert response.recommendations[0].requires_human_approval is False


def test_recommendations_infrastructure_overload():
    recommender = RecommendationAgent()
    rc = RootCauseCandidate(
        title="Device Hardware / Compute Resource Overload",
        description="Supervisor CPU pegged at 98%.",
        confidence=0.96,
        affected_devices=["edge-switch-01"],
    )
    corr_msg = create_agent_message("T-OVERLOAD", "correlation_agent", metadata={"probable_root_cause": rc.model_dump()})

    response = recommender.generate_recommendations("T-OVERLOAD", corr_msg)
    assert len(response.recommendations) >= 3

    titles = [r.title for r in response.recommendations]
    assert any("Top CPU Processes" in t for t in titles)
    assert any("CoPP" in t or "Policing" in t for t in titles)
    assert any("Restart" in t or "Daemon" in t for t in titles)

    # CoPP / Restart should require human approval
    disruptive = [r for r in response.recommendations if r.requires_human_approval]
    assert len(disruptive) >= 1
    assert any("Verify" in p or "backup" in p.lower() for p in disruptive[0].prerequisites)
    assert len(disruptive[0].rollback_steps) >= 1


def test_recommendations_wireless_degradation():
    recommender = RecommendationAgent()
    rc = RootCauseCandidate(
        title="Wireless RF Attenuation / Weak Wi-Fi Coverage",
        description="RSSI -84 dBm with packet drops.",
        confidence=0.92,
        affected_devices=["laptop-client-01"],
    )
    corr_msg = create_agent_message("T-WIFI", "correlation_agent", metadata={"probable_root_cause": rc.model_dump()})

    response = recommender.generate_recommendations("T-WIFI", corr_msg)
    assert len(response.recommendations) >= 3

    titles = [r.title for r in response.recommendations]
    assert any("Wireless RF Signal" in t or "Roaming" in t for t in titles)
    assert any("Steer Client" in t or "Transmit Power" in t for t in titles)
    assert any("Channel Width" in t or "DFS" in t for t in titles)


def test_recommendations_dhcp_failure():
    recommender = RecommendationAgent()
    rc = RootCauseCandidate(
        title="DHCP Service Failure / Scope Exhaustion",
        description="Pool address pool full.",
        confidence=0.94,
        affected_devices=["pc-finance-01", "pc-finance-02"],
    )
    corr_msg = create_agent_message("T-DHCP", "correlation_agent", metadata={"probable_root_cause": rc.model_dump()})

    response = recommender.generate_recommendations("T-DHCP", corr_msg)
    titles = [r.title for r in response.recommendations]
    assert any("Release and Renew" in t for t in titles)
    assert any("Expand DHCP Scope" in t for t in titles)
    assert any("Relay Helper" in t for t in titles)

    # Scope expansion is high risk and requires human approval
    scope_act = [r for r in response.recommendations if "Expand DHCP Scope" in r.title][0]
    assert scope_act.execution_risk == ExecutionRisk.HIGH.value
    assert scope_act.requires_human_approval is True
    assert len(scope_act.rollback_steps) >= 1


# ---------------------------------------------------------------------------
# MILESTONE 7 TESTS: INSUFFICIENT EVIDENCE & LOW CONFIDENCE SAFEGUARDS
# ---------------------------------------------------------------------------

def test_recommendations_insufficient_evidence():
    recommender = RecommendationAgent()
    rc = RootCauseCandidate(
        title="Indeterminate Root Cause (Insufficient Evidence)",
        description="Isolated telemetry symptom without corroboration.",
        confidence=0.25,
        affected_devices=["unknown-dev"],
    )
    corr_msg = create_agent_message("T-INDET", "correlation_agent", metadata={"probable_root_cause": rc.model_dump()})

    response = recommender.generate_recommendations("T-INDET", corr_msg)
    assert len(response.recommendations) >= 2

    # CRITICAL SAFEGUARD: Do not recommend disruptive remediation without sufficient evidence!
    for act in response.recommendations:
        assert act.action_type == ActionType.DIAGNOSTIC.value
        assert act.execution_risk == ExecutionRisk.LOW.value
        assert act.requires_human_approval is False

    assert any("Packet Capture" in r.title for r in response.recommendations)
    assert any("Polling Frequency" in r.title for r in response.recommendations)


def test_recommendations_low_confidence_fallback():
    recommender = RecommendationAgent()
    # Hypothesis with low confidence (0.20) should fallback to safe diagnostic actions
    rc = RootCauseCandidate(
        title="Potential Network Bandwidth Congestion",
        description="Weak signal of congestion.",
        confidence=0.20,
        affected_devices=["edge-1"],
    )
    corr_msg = create_agent_message("T-LOW", "correlation_agent", confidence=0.20, metadata={"probable_root_cause": rc.model_dump()})

    response = recommender.generate_recommendations("T-LOW", corr_msg)
    # Must NOT generate disruptive configuration or capacity changes
    for act in response.recommendations:
        assert act.execution_risk == ExecutionRisk.LOW.value
        assert act.requires_human_approval is False


# ---------------------------------------------------------------------------
# MILESTONE 7 TESTS: COMPETING HYPOTHESES & UNCERTAINTY
# ---------------------------------------------------------------------------

def test_recommendations_multiple_competing_hypotheses():
    recommender = RecommendationAgent()
    rc_primary = RootCauseCandidate(
        title="Network Bandwidth Congestion & Bufferbloat",
        description="Congestion detected.",
        confidence=0.75,
        affected_devices=["core-router-01"],
    )
    rc_alt = RootCauseCandidate(
        title="Device Hardware / Compute Resource Overload",
        description="Pegged CPU observed.",
        confidence=0.72,
        affected_devices=["core-router-01"],
    )
    corr_msg = create_agent_message(
        "T-COMP",
        "correlation_agent",
        metadata={
            "probable_root_cause": rc_primary.model_dump(),
            "alternative_causes": [rc_alt.model_dump()],
        },
    )

    response = recommender.generate_recommendations("T-COMP", corr_msg)
    titles = [r.title for r in response.recommendations]
    # Must contain a disambiguation action to prevent misdirected remediation
    assert any("Disambiguate" in t for t in titles)
    disambig = [r for r in response.recommendations if "Disambiguate" in r.title][0]
    assert disambig.execution_risk == ExecutionRisk.LOW.value


# ---------------------------------------------------------------------------
# MILESTONE 7 TESTS: PRIORITIZATION & DEDUPLICATION
# ---------------------------------------------------------------------------

def test_recommendations_prioritization_and_deduplication():
    recommender = RecommendationAgent()
    rc = RootCauseCandidate(
        title="Physical Interface / Cable Failure",
        description="Interface flapping with CRC errors.",
        confidence=0.92,
        affected_devices=["sw-01"],
    )
    corr_msg = create_agent_message("T-PRIO", "correlation_agent", metadata={"probable_root_cause": rc.model_dump()})

    response = recommender.generate_recommendations("T-PRIO", corr_msg)
    # Check that duplicates were suppressed
    titles = [r.title for r in response.recommendations]
    assert len(titles) == len(set(titles))

    # Check prioritization: Diagnostic/Low-risk action comes before disruptive action
    first_act = response.recommendations[0]
    assert first_act.action_type == ActionType.DIAGNOSTIC.value
    assert first_act.execution_risk == ExecutionRisk.LOW.value


# ---------------------------------------------------------------------------
# MILESTONE 7 TESTS: MULTI-DEVICE HANDLING & METADATA
# ---------------------------------------------------------------------------

def test_recommendations_multiple_affected_devices():
    recommender = RecommendationAgent()
    rc = RootCauseCandidate(
        title="DNS Resolver Outage or Misconfiguration",
        description="DNS outage.",
        confidence=0.95,
        affected_devices=["client-10", "client-11", "client-12", "server-app-01"],
    )
    corr_msg = create_agent_message("T-MDEV", "correlation_agent", metadata={"probable_root_cause": rc.model_dump()})

    response = recommender.generate_recommendations("T-MDEV", corr_msg)
    assert len(response.recommendations) >= 2
    for act in response.recommendations:
        assert len(act.affected_devices) == 4
        assert "server-app-01" in act.affected_devices


# ---------------------------------------------------------------------------
# MILESTONE 7 TESTS: RESILIENCE TO EMPTY / MALFORMED INPUTS
# ---------------------------------------------------------------------------

def test_recommendations_empty_and_malformed_input():
    recommender = RecommendationAgent()

    # Empty None input
    resp_empty = recommender.generate_recommendations("T-NONE", None)
    assert resp_empty.status == AgentStatus.SUCCESS
    assert len(resp_empty.recommendations) >= 1
    assert resp_empty.requires_human_approval is False

    # Malformed dictionary input missing metadata
    resp_malformed = recommender.generate_recommendations("T-MAL", {"random_key": 123})
    assert resp_malformed.status == AgentStatus.SUCCESS
    assert len(resp_malformed.recommendations) >= 1


# ---------------------------------------------------------------------------
# MILESTONE 7 TESTS: SCHEMA VALIDATION & JSON SERIALIZATION
# ---------------------------------------------------------------------------

def test_recommendations_response_schema_and_json():
    recommender = RecommendationAgent()
    rc = RootCauseCandidate(
        title="Network Bandwidth Congestion & Bufferbloat",
        description="Congestion.",
        confidence=0.90,
        affected_devices=["core-01"],
    )
    corr_msg = create_agent_message("T-SCHEMA", "correlation_agent", metadata={"probable_root_cause": rc.model_dump()})

    response = recommender.generate_recommendations("T-SCHEMA", corr_msg)
    assert isinstance(response, RecommendationAgentResponse)

    # Test JSON serialization
    json_str = response.model_dump_json()
    parsed = json.loads(json_str)
    assert parsed["agent_id"] == "recommendation_agent"
    assert parsed["requires_human_approval"] is True
    assert len(parsed["recommendations"]) >= 3

    # Test AgentMessage adapter
    agent_msg = response.to_agent_message()
    assert isinstance(agent_msg, AgentMessage)
    assert agent_msg.agent_id == "recommendation_agent"
    assert "actions" in agent_msg.metadata
    assert "requires_human_approval" in agent_msg.metadata

    # Validate message protocol accepts response
    validated = validate_message(response)
    assert isinstance(validated, AgentMessage)
