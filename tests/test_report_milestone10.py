"""
Tests for Milestone 10 — Unified Diagnostic Report Improvements.

Validates:
- Section A: Report Metadata (diagnosis_id, execution_timestamp, schema_version 2.0.0, duration, statuses)
- Section B: Executive Summary (condition, fault_detected, primary root cause, confidence, device count, agent tally)
- Section C: Agent Execution Summary (per-agent status, duration, findings, error details)
- Section D: Evidence and Findings (finding_id, source_agent, device/interface, metrics, severity, timestamp, OBSERVED_EVIDENCE vs INFERRED_HYPOTHESIS)
- Section E: Root-Cause Analysis (category, confidence, supporting evidence, supporting agents, alternative hypotheses, contradictions, uncertainty)
- Section F: Corrective Recommendations (title, priority, execution_risk, affected_device, human approval, preconditions, verification, rollback)
- Section G: Limitations and Warnings (ReportLimitations model: missing telemetry, invalid records, failed agents, stale observations, contradictions, warnings)
- Confidence presentation & certainty tiers (CALIBRATED_HEURISTIC_SCORE, CONFIRMED, PROVISIONAL, INDETERMINATE, NOMINAL)
- JSON serialization, persistence, and 100% backward compatibility
"""

from datetime import datetime, timezone
import json
import pytest
import pandas as pd

from communication.models import (
    AgentMessage,
    AgentStatus,
    Finding,
    EvidenceItem,
    Severity,
)
from data.scenarios import generate_scenario_data
from diagnosis.models import (
    DiagnosticReport,
    ReportLimitations,
    RootCauseCandidate,
    CorrectiveAction,
    NetworkHealthStatus,
)
from orchestrator.orchestrator import CentralOrchestrator


@pytest.fixture
def orchestrator(tmp_path):
    orch = CentralOrchestrator()
    orch.reports_dir = tmp_path / "test_reports"
    orch.reports_dir.mkdir(parents=True, exist_ok=True)
    return orch


def test_section_a_report_metadata(orchestrator):
    """Section A: Validate unique diagnosis_id, ISO 8601 timestamp with tz, schema_version 2.0.0, duration, and status."""
    data = generate_scenario_data("normal")
    report = orchestrator.run_diagnosis(data, scenario_name="test_normal", save_report=True)

    # 1. Unique diagnosis_id & report_id
    assert report.diagnosis_id is not None
    assert report.diagnosis_id.startswith("REP-") or report.diagnosis_id.startswith("DIAG-")
    assert report.report_id == report.diagnosis_id

    # 2. ISO 8601 Timestamp with timezone
    assert report.execution_timestamp is not None
    assert report.execution_timestamp.tzinfo is not None
    assert report.timestamp == report.execution_timestamp
    iso_str = report.execution_timestamp.isoformat()
    assert "+00:00" in iso_str or "Z" in iso_str

    # 3. Schema & Report Version
    assert report.schema_version == "2.0.0"
    assert report.report_version == "2.0.0"

    # 4. Execution duration
    assert report.execution_duration_ms is not None
    assert report.execution_duration_ms >= 0.0

    # 5. Diagnosis status
    assert report.overall_status in ["COMPLETED", "COMPLETED_WITH_WARNINGS"]
    assert report.execution_status == report.overall_status


def test_section_b_executive_summary_fault_scenario(orchestrator):
    """Section B: Executive summary for fault scenario contains fault detection, root cause, device count, and agent tally."""
    data = generate_scenario_data("dns_failure")
    report = orchestrator.run_diagnosis(data, scenario_name="test_dns", save_report=False)

    assert report.fault_detected is True
    assert report.overall_network_health in [NetworkHealthStatus.DEGRADED, NetworkHealthStatus.CRITICAL]
    assert report.selected_root_cause is not None
    assert "DNS" in report.selected_root_cause.title

    # Summary text validation
    summary = report.summary
    assert "Network condition:" in summary
    assert "Active fault detected" in summary
    assert "Primary root cause:" in summary
    assert "Overall confidence:" in summary
    assert "Affected devices:" in summary
    assert "Agents:" in summary
    assert "succeeded" in summary

    # Confidence and certainty
    assert 0.0 <= report.confidence <= 1.0
    assert report.confidence_score == report.confidence
    assert report.selected_root_cause.confidence == report.confidence
    assert report.diagnosis_certainty in ["CONFIRMED", "PROVISIONAL"]
    assert report.confidence_interpretation == "CALIBRATED_HEURISTIC_SCORE"


def test_section_b_executive_summary_healthy_scenario(orchestrator):
    """Section B: Healthy baseline scenario has fault_detected=False, certainty=NOMINAL."""
    data = generate_scenario_data("normal")
    report = orchestrator.run_diagnosis(data, scenario_name="test_healthy", save_report=False)

    assert report.fault_detected is False
    assert report.overall_network_health == NetworkHealthStatus.HEALTHY
    assert report.health_classification == "NOMINAL"
    assert report.diagnosis_certainty == "NOT_APPLICABLE"
    assert report.root_cause_confidence is None
    assert "nominal conditions" in report.summary or "No active faults detected" in report.summary


def test_section_c_agent_execution_summary(orchestrator):
    """Section C: Agent execution summary contains status, duration, finding count, errors for each agent."""
    data = generate_scenario_data("congestion")
    report = orchestrator.run_diagnosis(data, scenario_name="test_summary", save_report=False)

    summary_map = report.agent_execution_summary
    assert "performance_agent" in summary_map
    assert "infrastructure_agent" in summary_map
    assert "connectivity_agent" in summary_map

    for agent_id, a_sum in summary_map.items():
        assert "status" in a_sum
        assert a_sum["status"] in ["SUCCESS", "ERROR", "TIMEOUT", "INSUFFICIENT_DATA"]
        assert "duration_ms" in a_sum
        assert a_sum["duration_ms"] >= 0.0
        assert "finding_count" in a_sum
        assert isinstance(a_sum["finding_count"], int)
        assert "errors" in a_sum

    assert len(report.successful_agents) > 0
    assert isinstance(report.failed_agents, list)
    assert isinstance(report.timed_out_agents, list)


def test_section_d_evidence_and_findings_provenance(orchestrator):
    """Section D: Finding model distinguishes OBSERVED_EVIDENCE from INFERRED_HYPOTHESIS, has source_agent, devices, and metrics."""
    data = generate_scenario_data("congestion")
    report = orchestrator.run_diagnosis(data, scenario_name="test_findings", save_report=False)

    assert len(report.validated_findings) > 0

    for finding in report.validated_findings:
        assert finding.finding_id.startswith("FND-")
        assert finding.source_agent in ["performance_agent", "infrastructure_agent", "connectivity_agent"]
        assert finding.finding_type == "OBSERVED_EVIDENCE"
        assert finding.timestamp is not None
        assert isinstance(finding.affected_devices, list)
        assert finding.severity in [Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]

        # Metric validation
        if finding.metrics:
            assert finding.metric_name is not None
            assert finding.observed_value is not None


def test_section_e_root_cause_analysis_structure(orchestrator):
    """Section E: Selected root cause has category, confidence, supporting evidence, supporting agents, and uncertainty."""
    data = generate_scenario_data("infrastructure_overload")
    report = orchestrator.run_diagnosis(data, scenario_name="test_rc", save_report=False)

    rc = report.selected_root_cause
    assert rc is not None
    assert rc.title != ""
    assert rc.category != ""
    assert 0.0 <= rc.confidence <= 1.0
    assert len(rc.supporting_symptoms) > 0
    assert isinstance(rc.supporting_agents, list)
    assert isinstance(rc.affected_devices, list)
    assert isinstance(report.alternative_hypotheses, list)
    assert isinstance(report.conflicting_evidence, list)
    assert isinstance(report.uncertainty_notes, list)


def test_section_f_corrective_recommendations_fields(orchestrator):
    """Section F: Recommendations include title, priority, risk level, affected devices, human approval, preconditions, verification, rollback."""
    data = generate_scenario_data("interface_failure")
    report = orchestrator.run_diagnosis(data, scenario_name="test_actions", save_report=False)

    assert len(report.recommendations) > 0

    for action in report.recommendations:
        # Title and description
        assert action.title != ""
        assert action.action_title == action.title
        assert action.description != ""

        # Priority (1 to 5)
        assert 1 <= action.priority <= 5

        # Risk level
        assert action.execution_risk in ["LOW", "MEDIUM", "HIGH"]
        assert action.risk_level == action.execution_risk

        # Devices
        assert isinstance(action.affected_devices, list)
        if action.affected_devices:
            assert action.affected_device == action.affected_devices[0]

        # Approval flag
        assert isinstance(action.requires_human_approval, bool)

        # Preconditions / prerequisites
        assert isinstance(action.prerequisites, list)
        assert action.preconditions == action.prerequisites

        # Verification steps
        assert isinstance(action.verification_steps, list)
        assert len(action.verification_steps) > 0 or action.verification_step != ""

        # Rollback steps
        assert isinstance(action.rollback_steps, list)


def test_section_g_limitations_and_warnings(orchestrator):
    """Section G: ReportLimitations model captures missing telemetry, stale devices, invalid records, and warnings."""
    # Build telemetry with missing standard columns and older timestamp for a device
    stale_record = {
        "timestamp": "2026-10-31T10:00:00Z",
        "device_id": "core-router-01",
        "latency_ms": 12.0,
        "packet_loss_pct": 0.0,
    }
    recent_record = {
        "timestamp": "2026-10-31T10:10:00Z", # 10 minutes later (> 180s)
        "device_id": "edge-switch-01",
        "latency_ms": 15.0,
        "packet_loss_pct": 0.0,
    }

    report = orchestrator.run_diagnosis([stale_record, recent_record], scenario_name="test_limitations", save_report=False)

    limitations = report.limitations
    assert isinstance(limitations, ReportLimitations)
    assert isinstance(limitations.missing_telemetry, list)
    # CPU and memory were omitted in this custom record
    assert "cpu_utilization_pct" in limitations.missing_telemetry
    assert "memory_utilization_pct" in limitations.missing_telemetry

    # Stale device detection
    assert "core-router-01" in limitations.stale_observations
    assert any("core-router-01" in w for w in report.warnings)


def test_confidence_calibration_and_certainty_tiers():
    """Verify certainty tiers CONFIRMED, PROVISIONAL, INDETERMINATE, and NOMINAL."""
    # 1. High confidence fault -> CONFIRMED
    rep_high = DiagnosticReport(
        task_id="t1",
        overall_network_health=NetworkHealthStatus.CRITICAL,
        confidence=0.88,
        selected_root_cause=RootCauseCandidate(title="DNS Failure", category="CONNECTIVITY", confidence=0.88),
    )
    assert rep_high.diagnosis_certainty == "CONFIRMED"
    assert rep_high.fault_detected is True

    # 2. Moderate confidence fault -> PROVISIONAL
    rep_mod = DiagnosticReport(
        task_id="t2",
        overall_network_health=NetworkHealthStatus.DEGRADED,
        confidence=0.65,
        selected_root_cause=RootCauseCandidate(title="Transient Latency Spike", category="PERFORMANCE", confidence=0.65),
    )
    assert rep_mod.diagnosis_certainty == "PROVISIONAL"
    assert rep_mod.fault_detected is True

    # 3. Low confidence -> INDETERMINATE
    rep_low = DiagnosticReport(
        task_id="t3",
        overall_network_health=NetworkHealthStatus.DEGRADED,
        confidence=0.30,
        selected_root_cause=RootCauseCandidate(title="Ambiguous Packet Jitter", category="PERFORMANCE", confidence=0.30),
    )
    assert rep_low.diagnosis_certainty == "INDETERMINATE"
    assert rep_low.fault_detected is True

    # 4. Healthy network -> NOMINAL health, NOT_APPLICABLE hypothesis certainty
    rep_healthy = DiagnosticReport(
        task_id="t4",
        overall_network_health=NetworkHealthStatus.HEALTHY,
        confidence=0.95,
        selected_root_cause=RootCauseCandidate(title="Nominal Operations", category="NOMINAL", confidence=0.95),
    )
    assert rep_healthy.health_classification == "NOMINAL"
    assert rep_healthy.diagnosis_certainty == "NOT_APPLICABLE"
    assert rep_healthy.root_cause_confidence is None
    assert rep_healthy.fault_detected is False


def test_json_serialization_persistence_and_backward_compatibility(orchestrator):
    """Verify roundtrip JSON serialization, disk persistence, and legacy field compatibility."""
    data = generate_scenario_data("dns_failure")
    report = orchestrator.run_diagnosis(data, scenario_name="test_roundtrip", save_report=True)

    # 1. JSON dump & reload
    json_str = report.model_dump_json()
    parsed_dict = json.loads(json_str)

    # Validate essential keys in JSON output
    assert "diagnosis_id" in parsed_dict
    assert "schema_version" in parsed_dict
    assert "execution_duration_ms" in parsed_dict
    assert "fault_detected" in parsed_dict
    assert "diagnosis_certainty" in parsed_dict
    assert "confidence_interpretation" in parsed_dict
    assert "limitations" in parsed_dict
    assert "warnings" in parsed_dict

    # 2. Model re-validation from serialized JSON
    report_reloaded = DiagnosticReport.model_validate_json(json_str)
    assert report_reloaded.diagnosis_id == report.diagnosis_id
    assert report_reloaded.schema_version == "2.0.0"
    assert report_reloaded.fault_detected == report.fault_detected
    assert report_reloaded.confidence == report.confidence
    assert report_reloaded.limitations.missing_telemetry == report.limitations.missing_telemetry

    # 3. Disk persistence
    report_path = orchestrator.reports_dir / f"{report.report_id}.json"
    assert report_path.exists()
    with open(report_path, "r", encoding="utf-8") as f:
        disk_data = json.load(f)
    assert disk_data["report_id"] == report.report_id
    assert disk_data["schema_version"] == "2.0.0"

    # 4. Backward compatibility: legacy attributes work
    assert report.probable_root_cause.title == report.selected_root_cause.title
    assert report.confidence_score == report.confidence
    assert report.recommended_corrective_actions == report.recommendations
    assert report.alternative_causes == report.alternative_hypotheses
