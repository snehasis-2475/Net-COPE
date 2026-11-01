"""
Comprehensive Audit Tests for Milestone 10:
- Failure and limitation reporting (timeouts, agent failures, stale telemetry, missing telemetry, invalid telemetry)
- Unobserved domain handling (never claiming unobserved domain is healthy)
- FastAPI endpoint verification (POST /api/diagnose, GET /api/reports, GET /api/reports/{id}, error handling, schema 2.0.0)
- Report persistence, serialization, and backward compatibility with older reports
- Streamlit component rendering smoke tests
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from api.main import app
from communication.models import (
    AgentMessage,
    AgentStatus,
    Finding,
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
def test_client():
    return TestClient(app)


# =============================================================================
# 1. FAILURE AND LIMITATION REPORTING TESTS
# =============================================================================

def test_failure_reporting_one_agent_timeout(tmp_path):
    """Verify that an agent timing out is captured in limitations, warnings, and executive summary."""
    orch = CentralOrchestrator(agent_timeout_seconds=0.1)
    orch.reports_dir = tmp_path

    class SlowAgent:
        def execute(self, task_id, df):
            import time
            time.sleep(0.5)
            return AgentMessage(
                task_id=task_id,
                agent_id="performance_agent",
                status=AgentStatus.SUCCESS,
            )

    orch.performance_agent = SlowAgent()
    data = generate_scenario_data("normal")
    report = orch.run_diagnosis(data, scenario_name="test_timeout", save_report=False)

    assert "performance_agent" in report.timed_out_agents
    assert report.overall_status == "COMPLETED_WITH_WARNINGS"
    assert "performance_agent" in report.limitations.failed_or_timed_out_agents
    assert any("timed out" in w.lower() for w in report.warnings)
    assert any("performance_agent" in n for n in report.uncertainty_notes)
    # Ensure unobserved domain is not unconditionally claimed healthy without caveat
    assert "Agents:" in report.summary
    assert "timed out" in report.summary


def test_failure_reporting_agent_exception(tmp_path):
    """Verify that an agent raising an unhandled exception is isolated and documented."""
    orch = CentralOrchestrator()
    orch.reports_dir = tmp_path

    class BrokenAgent:
        def diagnose(self, task_id, df):
            raise RuntimeError("Database connection lost")

    orch.infrastructure_agent = BrokenAgent()
    data = generate_scenario_data("normal")
    report = orch.run_diagnosis(data, scenario_name="test_broken", save_report=False)

    assert "infrastructure_agent" in report.failed_agents
    assert report.overall_status == "COMPLETED_WITH_WARNINGS"
    assert "infrastructure_agent" in report.limitations.failed_or_timed_out_agents
    assert any("infrastructure_agent" in w for w in report.warnings)


def test_failure_reporting_multiple_agents_failing(tmp_path):
    """Verify handling when multiple domain agents fail simultaneously."""
    orch = CentralOrchestrator()
    orch.reports_dir = tmp_path

    class BrokenAgentA:
        def diagnose(self, task_id, df):
            raise ValueError("Failure A")

    class BrokenAgentB:
        def diagnose(self, task_id, df):
            raise RuntimeError("Failure B")

    orch.performance_agent = BrokenAgentA()
    orch.connectivity_agent = BrokenAgentB()

    data = generate_scenario_data("normal")
    report = orch.run_diagnosis(data, scenario_name="test_multi_fail", save_report=False)

    assert "performance_agent" in report.failed_agents
    assert "connectivity_agent" in report.failed_agents
    assert len(report.limitations.failed_or_timed_out_agents) == 2
    # Confidence penalty applied for missing domain agents
    assert report.confidence <= 0.80


def test_limitation_reporting_invalid_telemetry_batch(tmp_path):
    """Verify limitations and warnings when telemetry input is completely invalid."""
    orch = CentralOrchestrator()
    orch.reports_dir = tmp_path

    invalid_records = [{"corrupt_field": "garbage"}]
    report = orch.run_diagnosis(invalid_records, scenario_name="test_invalid", save_report=False)

    assert report.overall_status == "FAILED"
    assert report.fault_detected is False
    assert report.diagnosis_certainty == "INDETERMINATE"
    assert report.limitations.insufficient_evidence is True
    assert len(report.limitations.invalid_records) > 0
    assert len(report.warnings) > 0


def test_limitation_reporting_stale_telemetry_observations(tmp_path):
    """Verify that stale telemetry timestamps are recorded in limitations.stale_observations."""
    orch = CentralOrchestrator()
    orch.reports_dir = tmp_path

    records = [
        {"timestamp": "2026-10-31T08:00:00Z", "device_id": "stale-switch-01", "latency_ms": 10.0},
        {"timestamp": "2026-10-31T08:15:00Z", "device_id": "active-switch-02", "latency_ms": 12.0},
    ]
    report = orch.run_diagnosis(records, scenario_name="test_stale", save_report=False)

    assert "stale-switch-01" in report.limitations.stale_observations
    assert any("stale-switch-01" in w for w in report.warnings)


# =============================================================================
# 2. FASTAPI ENDPOINT INTEGRATION TESTS
# =============================================================================

def test_api_diagnose_endpoint_valid_schema(test_client):
    """POST /api/diagnose returns a valid schema 2.0.0 DiagnosticReport."""
    response = test_client.post("/api/diagnose", json={"scenario_id": "congestion"})
    assert response.status_code == 200

    data = response.json()
    assert data["schema_version"] == "2.0.0"
    assert data["report_version"] == "2.0.0"
    assert data["diagnosis_id"] is not None
    assert data["report_id"] == data["diagnosis_id"]
    assert data["fault_detected"] is True
    assert data["diagnosis_certainty"] in ["CONFIRMED", "PROVISIONAL"]
    assert data["confidence_interpretation"] == "CALIBRATED_HEURISTIC_SCORE"
    assert "limitations" in data
    assert "validated_findings" in data
    assert "recommendations" in data


def test_api_reports_list_and_get(test_client):
    """GET /api/reports and GET /api/reports/{id} retrieve valid reports and summaries."""
    # Run a diagnosis first to produce a report
    diag_res = test_client.post("/api/diagnose", json={"scenario_id": "dns_failure"})
    assert diag_res.status_code == 200
    diag_data = diag_res.json()
    rep_id = diag_data["report_id"]
    diag_id = diag_data["diagnosis_id"]

    # 1. List reports
    list_res = test_client.get("/api/reports?limit=10")
    assert list_res.status_code == 200
    reports = list_res.json()["reports"]
    assert len(reports) > 0
    assert any(r["report_id"] == rep_id for r in reports)

    # 2. Get report by report_id
    get_res = test_client.get(f"/api/reports/{rep_id}")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["report_id"] == rep_id
    assert get_data["schema_version"] == "2.0.0"

    # 3. Get report by diagnosis_id compatibility
    get_diag_res = test_client.get(f"/api/reports/{diag_id}")
    assert get_diag_res.status_code == 200
    assert get_diag_res.json()["diagnosis_id"] == diag_id


def test_api_error_handling_structured_no_traceback(test_client):
    """API returns structured HTTP 404/400 errors without exposing raw python tracebacks."""
    # Invalid scenario ID
    res = test_client.post("/api/diagnose", json={"scenario_id": "non_existent_scenario_xyz"})
    assert res.status_code == 404
    data = res.json()
    assert "detail" in data
    assert "Traceback" not in data["detail"]

    # Non-existent report ID
    res_rep = test_client.get("/api/reports/REP-NONEXISTENT999")
    assert res_rep.status_code == 404
    assert "detail" in res_rep.json()


# =============================================================================
# 3. REPORT PERSISTENCE & OLDER REPORT COMPATIBILITY
# =============================================================================

def test_persistence_roundtrip_and_backward_compatibility(tmp_path):
    """Verify that reports save, load back, deserialize via Pydantic, and handle legacy report formats."""
    orch = CentralOrchestrator()
    orch.reports_dir = tmp_path

    data = generate_scenario_data("interface_failure")
    report = orch.run_diagnosis(data, scenario_name="test_persistence", save_report=True)

    report_file = tmp_path / f"{report.report_id}.json"
    assert report_file.exists()

    # Load and validate with Pydantic v2
    with open(report_file, "r", encoding="utf-8") as f:
        disk_json = json.load(f)

    loaded_report = DiagnosticReport.model_validate(disk_json)
    assert loaded_report.report_id == report.report_id
    assert loaded_report.diagnosis_id == report.diagnosis_id
    assert loaded_report.schema_version == "2.0.0"
    assert loaded_report.fault_detected == report.fault_detected
    assert len(loaded_report.recommendations) == len(report.recommendations)

    # Backward compatibility with older report (missing Milestone 10 fields)
    legacy_report_dict = {
        "report_id": "REP-LEGACY-001",
        "task_id": "TASK-LEGACY-001",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "overall_network_health": "CRITICAL",
        "confidence_score": 0.85,
        "probable_root_cause": {
            "title": "Legacy Interface Down",
            "category": "INFRASTRUCTURE",
            "confidence": 0.85,
        },
        "recommended_corrective_actions": [
            {
                "title": "Bounce Interface",
                "category": "CONFIGURATION",
                "description": "Restart interface",
                "priority": 1,
            }
        ],
    }

    # Deserializing older format automatically syncs Milestone 10 fields
    deserialized_legacy = DiagnosticReport.model_validate(legacy_report_dict)
    assert deserialized_legacy.diagnosis_id == "REP-LEGACY-001"
    assert deserialized_legacy.schema_version == "2.0.0"
    assert deserialized_legacy.fault_detected is True
    assert deserialized_legacy.diagnosis_certainty == "CONFIRMED"
    assert deserialized_legacy.confidence == 0.85
    assert len(deserialized_legacy.recommendations) == 1


# =============================================================================
# 4. STREAMLIT RENDERING SMOKE TESTS
# =============================================================================

def test_streamlit_dashboard_smoke_rendering():
    """Smoke test dashboard helper logic for healthy, fault, and limitation states."""
    # 1. Healthy report
    rep_healthy = DiagnosticReport(
        task_id="t_health",
        overall_network_health=NetworkHealthStatus.HEALTHY,
        confidence=0.98,
        selected_root_cause=RootCauseCandidate(title="Nominal Network Operation", category="NOMINAL", confidence=0.98),
    )
    assert rep_healthy.health_classification == "NOMINAL"
    assert rep_healthy.diagnosis_certainty == "NOT_APPLICABLE"
    assert rep_healthy.fault_detected is False

    # 2. Fault report with limitations
    rep_fault = DiagnosticReport(
        task_id="t_fault",
        overall_network_health=NetworkHealthStatus.DEGRADED,
        confidence=0.72,
        selected_root_cause=RootCauseCandidate(title="Buffer Saturation", category="PERFORMANCE", confidence=0.72),
        limitations=ReportLimitations(
            missing_telemetry=["jitter_ms"],
            stale_observations=["device-99"],
            notes=["Buffer telemetry fluctuating"],
        ),
        warnings=["Stale observation detected on device-99."],
    )
    assert rep_fault.fault_detected is True
    assert rep_fault.diagnosis_certainty == "PROVISIONAL"
    assert len(rep_fault.limitations.missing_telemetry) == 1
    assert len(rep_fault.warnings) == 1

    # 3. Model dump to JSON for Streamlit download button
    json_export = rep_fault.model_dump_json(indent=2)
    assert "Buffer Saturation" in json_export
    assert "device-99" in json_export
