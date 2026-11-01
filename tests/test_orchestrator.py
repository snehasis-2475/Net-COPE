import time
from typing import Any, Dict, List
import pytest

from communication.models import (
    AgentMessage,
    AgentStatus,
    Finding,
    NetworkTelemetryRecord,
    Severity,
)
from communication.protocol import create_agent_message
from data.scenarios import generate_scenario_data
from diagnosis.models import NetworkHealthStatus, RootCauseCandidate
from orchestrator.orchestrator import CentralOrchestrator


# ---------------------------------------------------------------------------
# MOCK AGENTS FOR DETERMINISTIC TESTING
# ---------------------------------------------------------------------------

class MockTimeoutAgent:
    """Agent that deliberately sleeps longer than the orchestrator timeout."""
    def __init__(self, sleep_duration: float = 1.2):
        self.sleep_duration = sleep_duration
        self.finished = False

    def analyze(self, task_id: str, df: Any) -> AgentMessage:
        time.sleep(self.sleep_duration)
        self.finished = True
        return create_agent_message(
            task_id=task_id,
            agent_id="performance_agent",
            status=AgentStatus.SUCCESS,
        )


class MockExceptionAgent:
    """Agent that raises an unhandled exception."""
    def __init__(self, error_message: str = "Simulated crash in agent"):
        self.error_message = error_message

    def analyze(self, task_id: str, df: Any) -> AgentMessage:
        raise RuntimeError(self.error_message)


class MockInvalidSchemaAgent:
    """Agent that returns an invalid or malformed response."""
    def __init__(self, bad_payload: Any = None):
        self.bad_payload = bad_payload if bad_payload is not None else {"invalid": "payload"}

    def analyze(self, task_id: str, df: Any) -> Any:
        return self.bad_payload


class MockDuplicateMessageAgent:
    """Agent that returns a fixed message_id to test duplicate detection."""
    def __init__(self, duplicate_id: str = "FIXED-MSG-ID-001", agent_id: str = "performance_agent"):
        self.duplicate_id = duplicate_id
        self.agent_id = agent_id

    def analyze(self, task_id: str, df: Any) -> AgentMessage:
        msg = create_agent_message(
            task_id=task_id,
            agent_id=self.agent_id,
            status=AgentStatus.SUCCESS,
        )
        msg.message_id = self.duplicate_id
        return msg


# ---------------------------------------------------------------------------
# SECTION 1: EXECUTION RELIABILITY & TIMEOUT BEHAVIOR
# ---------------------------------------------------------------------------

def test_1_all_agents_succeed(tmp_path):
    """Test 1: All agents execute successfully under normal conditions."""
    orchestrator = CentralOrchestrator(reports_dir=str(tmp_path))
    telemetry = generate_scenario_data("normal")

    report = orchestrator.run_diagnosis(telemetry=telemetry, scenario_name="normal")

    assert report.overall_status == "COMPLETED"
    assert report.execution_status == "COMPLETED"
    assert report.overall_network_health == NetworkHealthStatus.HEALTHY
    assert report.confidence >= 0.90
    assert len(report.successful_agents) == 3  # domain agents
    assert len(report.failed_agents) == 0
    assert len(report.timed_out_agents) == 0
    assert len(report.rejected_messages) == 0
    assert len(report.individual_agent_findings) == 5
    assert (tmp_path / f"{report.diagnosis_id}.json").exists()


def test_2_timeout_bounded_execution_and_isolation(tmp_path):
    """
    CRITICAL REGRESSION TEST:
    Demonstrates:
    1. Orchestrator returns within bounded time after configured timeout (does NOT block on shutdown).
    2. Timed-out agent is correctly recorded in timed_out_agents.
    3. Other agents' successful results are preserved.
    4. Late worker completion cannot corrupt or mutate the returned report.
    5. Safe non-blocking executor lifecycle is used (no unsafe thread killing).
    """
    # Configure timeout of 0.25s while mock agent deliberately sleeps 1.5s
    blocked_agent = MockTimeoutAgent(sleep_duration=1.5)
    orchestrator = CentralOrchestrator(
        agent_timeout_seconds=0.25,
        reports_dir=str(tmp_path),
        performance_agent=blocked_agent,
    )
    telemetry = generate_scenario_data("normal")

    t0 = time.perf_counter()
    report = orchestrator.run_diagnosis(telemetry=telemetry)
    return_duration = time.perf_counter() - t0

    # 1. Returned within bounded time (far below the 1.5s sleep of the blocked agent)
    assert return_duration < 0.85, (
        f"Orchestrator blocked on shutdown! Took {return_duration:.3f}s for 0.25s timeout."
    )

    # 2. Timed-out agent correctly identified and recorded
    assert "performance_agent" in report.timed_out_agents
    assert report.overall_status == "COMPLETED_WITH_WARNINGS"
    perf_msg = report.individual_agent_findings["performance_agent"]
    assert perf_msg.status == AgentStatus.TIMEOUT
    assert any("timeout" in err.lower() for err in perf_msg.errors)

    # 3. Successful results from concurrent agents preserved
    assert "infrastructure_agent" in report.successful_agents
    assert "connectivity_agent" in report.successful_agents
    assert report.selected_root_cause is not None

    # Snapshot report state at return time
    snapshot_msg_status = report.individual_agent_findings["performance_agent"].status
    snapshot_confidence = report.confidence
    snapshot_findings_count = len(report.validated_findings)

    # 4. Wait for background thread to finish its sleep and verify report is immutable
    time.sleep(1.35)
    assert blocked_agent.finished is True, "Background worker thread did not finish cleanly"
    assert report.individual_agent_findings["performance_agent"].status == snapshot_msg_status
    assert report.confidence == snapshot_confidence
    assert len(report.validated_findings) == snapshot_findings_count


def test_3_one_agent_raises_exception(tmp_path):
    """Test 3: An agent throws an unhandled exception without crashing orchestration."""
    broken_agent = MockExceptionAgent("Fatal crash in infrastructure agent")
    orchestrator = CentralOrchestrator(
        reports_dir=str(tmp_path),
        infrastructure_agent=broken_agent,
    )
    telemetry = generate_scenario_data("normal")

    report = orchestrator.run_diagnosis(telemetry=telemetry)

    assert "infrastructure_agent" in report.failed_agents
    assert report.overall_status == "COMPLETED_WITH_WARNINGS"
    infra_msg = report.individual_agent_findings["infrastructure_agent"]
    assert infra_msg.status == AgentStatus.ERROR
    assert "Fatal crash" in infra_msg.errors[0]
    # Other agents still completed
    assert "performance_agent" in report.successful_agents
    assert "connectivity_agent" in report.successful_agents


def test_4_multiple_agents_fail(tmp_path):
    """Test 4: Multiple domain agents fail simultaneously, orchestrator still finishes."""
    orchestrator = CentralOrchestrator(
        reports_dir=str(tmp_path),
        performance_agent=MockExceptionAgent("Crash 1"),
        infrastructure_agent=MockExceptionAgent("Crash 2"),
    )
    telemetry = generate_scenario_data("normal")

    report = orchestrator.run_diagnosis(telemetry=telemetry)

    assert "performance_agent" in report.failed_agents
    assert "infrastructure_agent" in report.failed_agents
    assert len(report.failed_agents) == 2
    assert report.overall_status == "COMPLETED_WITH_WARNINGS"
    assert "connectivity_agent" in report.successful_agents
    assert report.selected_root_cause is not None
    assert any("missing or failed" in note for note in report.uncertainty_notes)


def test_5_invalid_agent_response(tmp_path):
    """Test 5: An agent returns an invalid response (non-AgentMessage object)."""
    orchestrator = CentralOrchestrator(
        reports_dir=str(tmp_path),
        performance_agent=MockInvalidSchemaAgent({"bad_key": 12345}),
    )
    telemetry = generate_scenario_data("normal")

    report = orchestrator.run_diagnosis(telemetry=telemetry)

    assert "performance_agent" in report.failed_agents
    assert len(report.rejected_messages) >= 1
    rejection = report.rejected_messages[0]
    assert rejection["agent_id"] == "performance_agent"
    assert "validation failed" in rejection["reason"].lower() or "schema" in rejection["reason"].lower()


def test_6_duplicate_agent_messages(tmp_path):
    """Test 6: Duplicate agent message_id is intercepted and rejected."""
    fixed_id = "MSG-DUP-12345"
    orchestrator = CentralOrchestrator(
        reports_dir=str(tmp_path),
        performance_agent=MockDuplicateMessageAgent(duplicate_id=fixed_id, agent_id="performance_agent"),
    )

    seen = {fixed_id}
    raw_msg = create_agent_message(task_id="T1", agent_id="performance_agent")
    raw_msg.message_id = fixed_id

    validated, rejection = orchestrator._validate_agent_message(
        raw_msg=raw_msg,
        expected_agent_id="performance_agent",
        task_id="T1",
        seen_message_ids=seen,
    )

    assert rejection is not None
    assert "Duplicate message detected" in rejection["reason"]
    assert validated.status == AgentStatus.ERROR


# ---------------------------------------------------------------------------
# SECTION 2: CONTRADICTION & CONFLICT RESOLUTION
# ---------------------------------------------------------------------------

def test_7_contradiction_a_packet_loss_with_successful_reachability(tmp_path):
    """Test A: Packet loss vs healthy reachability without link congestion."""
    orchestrator = CentralOrchestrator(reports_dir=str(tmp_path))

    telemetry = [
        {
            "device_id": "router-01",
            "timestamp": "2026-10-31T12:00:00Z",
            "latency_ms": 15.0,
            "packet_loss_pct": 0.0,
            "bandwidth_util_pct": 20.0,
            "connectivity_status": "connected",
            "dns_resolution_status": "success",
        }
    ]

    class MockContradictoryPerfAgent:
        def analyze(self, task_id: str, df: Any) -> AgentMessage:
            msg = create_agent_message(task_id=task_id, agent_id="performance_agent")
            msg.findings.append(
                Finding(
                    finding_id="F-PERF-LOSS",
                    category="PERFORMANCE",
                    title="Critical Packet Loss Detected",
                    description="Severe packet loss observed on device",
                    severity=Severity.CRITICAL,
                    affected_devices=["router-01"],
                    metrics={"packet_loss_pct": 25.0},
                )
            )
            return msg

    orchestrator.performance_agent = MockContradictoryPerfAgent()
    report = orchestrator.run_diagnosis(telemetry=telemetry)

    assert len(report.conflicting_evidence) >= 1
    conflict = next(c for c in report.conflicting_evidence if c["type"] == "PACKET_LOSS_VS_HEALTHY_REACHABILITY")
    assert "Hypothesis:" in conflict["resolution"]
    assert conflict["confidence_penalty"] == 0.10
    assert any("Contradiction on ['router-01']" in note for note in report.uncertainty_notes)


def test_8_contradiction_b_infra_offline_vs_verified_current_reachability(tmp_path):
    """Test B: Infrastructure reports offline while current telemetry confirms active reachability."""
    orchestrator = CentralOrchestrator(reports_dir=str(tmp_path))

    telemetry = [
        {
            "device_id": "switch-core-01",
            "timestamp": "2026-10-31T12:00:00Z",
            "connectivity_status": "connected",
            "dns_resolution_status": "success",
            "latency_ms": 10.0,
        }
    ]

    class MockOfflineInfraAgent:
        def analyze(self, task_id: str, df: Any) -> AgentMessage:
            msg = create_agent_message(task_id=task_id, agent_id="infrastructure_agent")
            msg.findings.append(
                Finding(
                    finding_id="F-INFRA-DOWN",
                    category="INFRASTRUCTURE",
                    title="Critical Device Offline",
                    description="Device reported completely down or unreachable",
                    severity=Severity.CRITICAL,
                    affected_devices=["switch-core-01"],
                    metrics={"device_status": "offline"},
                )
            )
            return msg

    orchestrator.infrastructure_agent = MockOfflineInfraAgent()
    report = orchestrator.run_diagnosis(telemetry=telemetry)

    conflict = next(c for c in report.conflicting_evidence if c["type"] == "DEVICE_OFFLINE_VS_REACHABLE")
    assert "Hypothesis:" in conflict["resolution"]
    assert conflict["confidence_penalty"] == 0.15
    assert any("Severe contradiction on ['switch-core-01']" in note for note in report.uncertainty_notes)


def test_9_contradiction_c_infra_offline_vs_stale_telemetry(tmp_path):
    """
    Test C: Infrastructure reports offline and device telemetry is stale.
    Telemetry presence alone does NOT prove current reachability when timestamps are stale.
    Therefore, NO contradiction B should be raised.
    """
    orchestrator = CentralOrchestrator(reports_dir=str(tmp_path))

    # Batch has current timestamp for router-01, but switch-old-01 telemetry is 15 minutes old (stale)
    telemetry = [
        {
            "device_id": "router-01",
            "timestamp": "2026-10-31T12:15:00Z",
            "connectivity_status": "connected",
            "dns_resolution_status": "success",
            "latency_ms": 10.0,
        },
        {
            "device_id": "switch-old-01",
            "timestamp": "2026-10-31T12:00:00Z",  # 15 minutes stale relative to batch max
            "connectivity_status": "connected",
            "dns_resolution_status": "success",
            "latency_ms": 10.0,
        },
    ]

    class MockOfflineInfraAgent:
        def analyze(self, task_id: str, df: Any) -> AgentMessage:
            msg = create_agent_message(task_id=task_id, agent_id="infrastructure_agent")
            msg.findings.append(
                Finding(
                    finding_id="F-INFRA-DOWN",
                    category="INFRASTRUCTURE",
                    title="Device Offline",
                    description="Device has stopped reporting and is down",
                    severity=Severity.CRITICAL,
                    affected_devices=["switch-old-01"],
                    metrics={"device_status": "offline"},
                )
            )
            return msg

    orchestrator.infrastructure_agent = MockOfflineInfraAgent()
    report = orchestrator.run_diagnosis(telemetry=telemetry)

    # Stale telemetry must NOT trigger a false contradiction against offline status
    offline_conflicts = [c for c in report.conflicting_evidence if c["type"] == "DEVICE_OFFLINE_VS_REACHABLE"]
    assert len(offline_conflicts) == 0, "Stale telemetry falsely triggered an offline vs reachable contradiction!"


def test_10_contradiction_d_congestion_vs_physical_interface_crc(tmp_path):
    """
    Test D: Performance reports congestion, while Infrastructure reports physical CRC framing errors.
    Physical layer errors take precedence over pure traffic bandwidth congestion.
    """
    orchestrator = CentralOrchestrator(reports_dir=str(tmp_path))

    class MockConflictPerfAgent:
        def analyze(self, task_id: str, df: Any) -> AgentMessage:
            msg = create_agent_message(task_id=task_id, agent_id="performance_agent")
            msg.findings.append(
                Finding(
                    finding_id="F-PERF-CONG",
                    category="PERFORMANCE",
                    title="Network Congestion and Packet Loss",
                    description="High buffer utilization",
                    severity=Severity.HIGH,
                    affected_devices=["core-rtr-01"],
                )
            )
            return msg

    class MockConflictInfraAgent:
        def analyze(self, task_id: str, df: Any) -> AgentMessage:
            msg = create_agent_message(task_id=task_id, agent_id="infrastructure_agent")
            msg.findings.append(
                Finding(
                    finding_id="F-INFRA-CRC",
                    category="INFRASTRUCTURE",
                    title="Interface Error CRC Drops",
                    description="Physical framing corruption",
                    severity=Severity.CRITICAL,
                    affected_devices=["core-rtr-01"],
                )
            )
            return msg

    orchestrator.performance_agent = MockConflictPerfAgent()
    orchestrator.infrastructure_agent = MockConflictInfraAgent()

    telemetry = [
        {
            "device_id": "core-rtr-01",
            "timestamp": "2026-10-31T12:00:00Z",
            "latency_ms": 40.0,
            "packet_loss_pct": 2.0,
            "crc_errors": 120,
        }
    ]

    report = orchestrator.run_diagnosis(telemetry=telemetry)

    conflict = next(c for c in report.conflicting_evidence if c["type"] == "CONGESTION_VS_PHYSICAL_FAILURE")
    assert "Hypothesis:" in conflict["resolution"]
    assert conflict["confidence_penalty"] == 0.10
    assert any("Disambiguated on ['core-rtr-01']" in note for note in report.uncertainty_notes)


def test_11_contradiction_e_competing_hypotheses_insufficient_evidence(tmp_path):
    """
    Test E: Competing root causes with insufficient corroborating evidence.
    Verifies that:
    1. Competing hypotheses are preserved rather than arbitrarily discarding plausible causes.
    2. Insufficient evidence yields appropriately cautious confidence (<= 0.60) without unjustifiable certainty.
    3. Non-disruptive diagnostic recommendations are formulated.
    """
    orchestrator = CentralOrchestrator(reports_dir=str(tmp_path))

    # Single isolated borderline metric (55ms latency) without corroborating drops or bandwidth spikes
    telemetry = [
        {
            "device_id": "workstation-04",
            "timestamp": "2026-10-31T12:00:00Z",
            "latency_ms": 55.0,
            "jitter_ms": 2.0,
            "packet_loss_pct": 0.0,
            "connectivity_status": "connected",
        }
    ]

    report = orchestrator.run_diagnosis(telemetry=telemetry)

    # Must preserve hypothesis structure
    assert report.selected_root_cause is not None
    assert "Indeterminate" in report.selected_root_cause.title or len(report.root_cause_hypotheses) >= 1
    # Cautious confidence (below decisive threshold 0.70)
    assert 0.10 <= report.confidence <= 0.60
    # Recommendations should be non-disruptive diagnostic actions
    assert len(report.recommendations) >= 1
    assert all(not rec.requires_human_approval for rec in report.recommendations if rec.execution_risk == "LOW")


# ---------------------------------------------------------------------------
# SECTION 3: INGESTION, MISSING AGENTS & CONFIDENCE INTEGRITY
# ---------------------------------------------------------------------------

def test_12_insufficient_evidence_handling(tmp_path):
    """Test 12: Empty or invalid telemetry cleanly yields FAILED status and 0.0 confidence."""
    orchestrator = CentralOrchestrator(reports_dir=str(tmp_path))
    report = orchestrator.run_diagnosis(telemetry=[])

    assert report.overall_status == "FAILED"
    assert report.confidence == 0.0
    assert report.confidence_score == 0.0
    assert "empty" in report.summary.lower()
    assert len(report.uncertainty_notes) >= 1


def test_13_missing_optional_agent(tmp_path):
    """Test 13: Orchestrator handles missing optional agent without failing."""
    orchestrator = CentralOrchestrator(
        reports_dir=str(tmp_path),
        infrastructure_agent=None,  # Missing optional agent
    )
    telemetry = generate_scenario_data("normal")

    report = orchestrator.run_diagnosis(telemetry=telemetry)

    assert report.overall_status == "COMPLETED"
    assert "infrastructure_agent" not in report.successful_agents
    assert "performance_agent" in report.successful_agents
    assert "connectivity_agent" in report.successful_agents
    assert report.selected_root_cause is not None


def test_14_partial_telemetry_failure(tmp_path):
    """Test 14: Ingestion isolates corrupt records and processes valid records."""
    orchestrator = CentralOrchestrator(reports_dir=str(tmp_path))

    mixed_telemetry = [
        # Valid record
        {
            "device_id": "router-01",
            "timestamp": "2026-10-31T12:00:00Z",
            "latency_ms": 25.0,
            "packet_loss_pct": 0.5,
            "cpu_utilization_percent": 30.0,
        },
        # Corrupt record 1: missing device_id
        {
            "timestamp": "2026-10-31T12:00:00Z",
            "latency_ms": 50.0,
        },
        # Corrupt record 2: negative latency
        {
            "device_id": "switch-01",
            "timestamp": "2026-10-31T12:00:00Z",
            "latency_ms": -99.0,
        },
    ]

    report = orchestrator.run_diagnosis(telemetry=mixed_telemetry)

    assert report.overall_status == "COMPLETED_WITH_WARNINGS"
    assert len(report.errors) >= 2  # 2 corrupt rows logged
    assert report.selected_root_cause is not None


def test_15_confidence_integrity_and_boundaries(tmp_path):
    """
    Test 15: Confidence integrity:
    - Stays within [0.0, 1.0].
    - Report-level confidence and selected_root_cause confidence are strictly identical.
    - Contradiction penalty reduces confidence appropriately without producing negative values.
    """
    orchestrator_base = CentralOrchestrator(reports_dir=str(tmp_path / "base"))
    telemetry = [
        {
            "device_id": "switch-01",
            "timestamp": "2026-10-31T12:00:00Z",
            "connectivity_status": "connected",
            "dns_resolution_status": "success",
            "latency_ms": 10.0,
            "packet_loss_pct": 0.0,
        }
    ]
    report_base = orchestrator_base.run_diagnosis(telemetry=telemetry)

    orchestrator_contra = CentralOrchestrator(reports_dir=str(tmp_path / "contra"))

    class MockOfflineInfraAgent:
        def analyze(self, task_id: str, df: Any) -> AgentMessage:
            msg = create_agent_message(task_id=task_id, agent_id="infrastructure_agent")
            msg.findings.append(
                Finding(
                    finding_id="F-INFRA-DOWN",
                    category="INFRASTRUCTURE",
                    title="Device Offline",
                    description="Device down",
                    severity=Severity.CRITICAL,
                    affected_devices=["switch-01"],
                )
            )
            return msg

    orchestrator_contra.infrastructure_agent = MockOfflineInfraAgent()
    report_contra = orchestrator_contra.run_diagnosis(telemetry=telemetry)

    assert report_contra.confidence < report_base.confidence
    assert len(report_contra.conflicting_evidence) >= 1
    assert report_contra.conflicting_evidence[0]["confidence_penalty"] == 0.15
    # Strict boundary checks
    assert 0.0 <= report_contra.confidence <= 1.0
    assert report_contra.confidence == report_contra.selected_root_cause.confidence
    assert report_contra.confidence_score == report_contra.confidence


def test_16_deterministic_conflict_resolution(tmp_path):
    """Test 16: Conflict resolution is strictly deterministic across repeated runs."""
    orchestrator = CentralOrchestrator(reports_dir=str(tmp_path))

    class MockConflictPerfAgent:
        def analyze(self, task_id: str, df: Any) -> AgentMessage:
            msg = create_agent_message(task_id=task_id, agent_id="performance_agent")
            msg.findings.append(
                Finding(
                    finding_id="F-PERF-CONG",
                    category="PERFORMANCE",
                    title="Network Congestion and Packet Loss",
                    description="High buffer utilization",
                    severity=Severity.HIGH,
                    affected_devices=["core-rtr-01"],
                )
            )
            return msg

    class MockConflictInfraAgent:
        def analyze(self, task_id: str, df: Any) -> AgentMessage:
            msg = create_agent_message(task_id=task_id, agent_id="infrastructure_agent")
            msg.findings.append(
                Finding(
                    finding_id="F-INFRA-CRC",
                    category="INFRASTRUCTURE",
                    title="Interface Error CRC Drops",
                    description="Physical framing corruption",
                    severity=Severity.CRITICAL,
                    affected_devices=["core-rtr-01"],
                )
            )
            return msg

    orchestrator.performance_agent = MockConflictPerfAgent()
    orchestrator.infrastructure_agent = MockConflictInfraAgent()

    telemetry = [
        {
            "device_id": "core-rtr-01",
            "timestamp": "2026-10-31T12:00:00Z",
            "latency_ms": 40.0,
            "packet_loss_pct": 2.0,
            "crc_errors": 120,
        }
    ]

    report_run1 = orchestrator.run_diagnosis(telemetry=telemetry)
    report_run2 = orchestrator.run_diagnosis(telemetry=telemetry)

    assert len(report_run1.conflicting_evidence) == len(report_run2.conflicting_evidence)
    assert report_run1.conflicting_evidence[0]["type"] == report_run2.conflicting_evidence[0]["type"]
    assert report_run1.confidence == report_run2.confidence


def test_17_backward_compatibility_with_existing_callers(tmp_path):
    """Test 17: Ensure full backward compatibility with older field names and models."""
    orchestrator = CentralOrchestrator(reports_dir=str(tmp_path))
    telemetry = generate_scenario_data("normal")

    report = orchestrator.run_diagnosis(telemetry=telemetry)

    # Legacy fields
    assert report.report_id == report.diagnosis_id
    assert report.execution_status == report.overall_status
    assert report.confidence_score == report.confidence
    assert report.probable_root_cause == report.selected_root_cause
    assert report.recommended_corrective_actions == report.recommendations
    assert report.alternative_causes == report.alternative_hypotheses
    # JSON serialization roundtrip
    json_str = report.model_dump_json()
    assert "diagnosis_id" in json_str
    assert "report_id" in json_str
