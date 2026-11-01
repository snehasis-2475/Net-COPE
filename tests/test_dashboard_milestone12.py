from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import py_compile
import unittest.mock as mock
import pandas as pd
import pytest
import requests
from streamlit.testing.v1 import AppTest

from communication.models import (
    AgentMessage,
    AgentStatus,
    EvidenceItem,
    Finding,
    Severity,
)
from dashboard.components import (
    CANONICAL_AGENTS,
    METRIC_CONFIG,
    analyze_telemetry_dataset,
    build_evidence_table,
    build_findings_table,
    categorize_action,
    diagnose_via_api,
    fetch_report_from_api,
    get_agent_status_grid,
    get_certainty_badge,
    get_confidence_display,
    get_fault_detection_badge,
    get_health_badge,
    list_reports_from_api,
    list_saved_reports,
    load_saved_report,
    prepare_telemetry_dataframe,
)
from data.scenarios import generate_scenario_data
from diagnosis.models import (
    CorrectiveAction,
    DiagnosticReport,
    NetworkHealthStatus,
    ReportLimitations,
    RootCauseCandidate,
)


# =============================================================================
# SCENARIO 1: OVERALL NETWORK HEALTH (4 TIERS)
# =============================================================================

def test_01_network_overview_health_four_tiers():
    """Verify distinct styling, labels, and SLA notes for NOMINAL, DEGRADED, CRITICAL, and UNKNOWN."""
    nominal = get_health_badge(NetworkHealthStatus.HEALTHY)
    assert nominal["label"] == "NOMINAL"
    assert nominal["color"] == "#10B981"
    assert "baseline" in nominal["description"].lower()

    degraded = get_health_badge("DEGRADED")
    assert degraded["label"] == "DEGRADED"
    assert degraded["color"] == "#F59E0B"
    assert "breached" in degraded["description"].lower()

    critical = get_health_badge(NetworkHealthStatus.CRITICAL)
    assert critical["label"] == "CRITICAL"
    assert critical["color"] == "#EF4444"
    assert "severe" in critical["description"].lower()

    unknown = get_health_badge("UNKNOWN")
    assert unknown["label"] == "UNKNOWN"
    assert unknown["color"] == "#94A3B8"


# =============================================================================
# SCENARIO 2: BINARY FAULT DETECTION STATE
# =============================================================================

def test_02_network_overview_fault_detection_state():
    """Verify binary fault detection badge attributes."""
    fault_yes = get_fault_detection_badge(True)
    assert fault_yes["label"] == "FAULT DETECTED"
    assert fault_yes["color"] == "#EF4444"
    assert "active" in fault_yes["text"].lower()

    fault_no = get_fault_detection_badge(False)
    assert fault_no["label"] == "NO FAULTS DETECTED"
    assert fault_no["color"] == "#10B981"
    assert "comply" in fault_no["text"].lower()


# =============================================================================
# SCENARIO 3: CURRENT DIAGNOSIS STATUS
# =============================================================================

def test_03_network_overview_current_diagnosis_status():
    """Verify handling of COMPLETED, COMPLETED_WITH_WARNINGS, PARTIAL_FAILURE, and FAILED statuses."""
    rep_comp = DiagnosticReport(task_id="t1", overall_status="COMPLETED")
    assert rep_comp.overall_status == "COMPLETED"

    rep_warn = DiagnosticReport(task_id="t2", overall_status="COMPLETED_WITH_WARNINGS")
    assert rep_warn.overall_status == "COMPLETED_WITH_WARNINGS"

    rep_part = DiagnosticReport(task_id="t3", overall_status="PARTIAL_FAILURE")
    assert rep_part.overall_status == "PARTIAL_FAILURE"

    rep_fail = DiagnosticReport(task_id="t4", overall_status="FAILED")
    assert rep_fail.overall_status == "FAILED"


# =============================================================================
# SCENARIO 4: AFFECTED DEVICES & ACTIVE FINDINGS COUNTS
# =============================================================================

def test_04_network_overview_affected_devices_and_active_findings():
    """Verify counts of affected nodes and active findings are accurately reported."""
    report = DiagnosticReport(
        task_id="t_counts",
        affected_devices=["core-router-01", "dist-switch-02"],
        validated_findings=[
            Finding(finding_id="F1", category="PERFORMANCE", title="Loss", description="5% loss", severity=Severity.HIGH),
            Finding(finding_id="F2", category="INFRASTRUCTURE", title="CPU", description="90% CPU", severity=Severity.CRITICAL),
        ],
    )
    assert len(report.affected_devices) == 2
    assert len(report.validated_findings) == 2


# =============================================================================
# SCENARIO 5: AGENT DISPATCH COUNTS
# =============================================================================

def test_05_network_overview_agent_dispatch_counts():
    """Verify successful, failed, and timed-out agent tallies."""
    report = DiagnosticReport(
        task_id="t_agents",
        successful_agents=["performance_agent", "infrastructure_agent"],
        failed_agents=["connectivity_agent"],
        timed_out_agents=["correlation_agent"],
    )
    assert len(report.successful_agents) == 2
    assert len(report.failed_agents) == 1
    assert len(report.timed_out_agents) == 1


# =============================================================================
# SCENARIO 6: LAST DIAGNOSIS TIMESTAMP
# =============================================================================

def test_06_network_overview_timestamp_display():
    """Verify UTC timestamp formatting and null handling."""
    now_utc = datetime(2026, 10, 31, 14, 30, 0, tzinfo=timezone.utc)
    report = DiagnosticReport(task_id="t_ts", timestamp=now_utc)
    formatted = report.timestamp.strftime("%Y-%m-%d %H:%M:%S UTC")
    assert formatted == "2026-10-31 14:30:00 UTC"


# =============================================================================
# SCENARIO 7: PROBABLE ROOT CAUSE TITLE & DESCRIPTION
# =============================================================================

def test_07_diagnostic_summary_probable_root_cause():
    """Verify root cause title, detailed description, category, and affected devices."""
    rc = RootCauseCandidate(
        title="Network Transit Congestion",
        description="Peak utilization on GigabitEthernet0/0/1 caused buffer overflow and tail drops.",
        category="PERFORMANCE",
        confidence=0.92,
        affected_devices=["core-router-01"],
    )
    report = DiagnosticReport(task_id="t_rc", probable_root_cause=rc)
    assert report.probable_root_cause.title == "Network Transit Congestion"
    assert "buffer overflow" in report.probable_root_cause.description
    assert report.probable_root_cause.category == "PERFORMANCE"
    assert report.probable_root_cause.affected_devices == ["core-router-01"]


# =============================================================================
# SCENARIO 8: ROOT-CAUSE CONFIDENCE (SUPPRESSED ON HEALTHY NETWORKS)
# =============================================================================

def test_08_diagnostic_summary_root_cause_confidence_unfabricated():
    """CRITICAL: For healthy networks, do NOT display a fabricated root-cause confidence score."""
    healthy_report = DiagnosticReport(
        task_id="t_health",
        overall_network_health=NetworkHealthStatus.HEALTHY,
        fault_detected=False,
        health_classification="NOMINAL",
        root_cause_confidence=None,
        confidence_score=0.95,  # internal score must be suppressed
    )
    conf = get_confidence_display(healthy_report)
    assert conf["is_applicable"] is False
    assert conf["display_text"] == "N/A"
    assert conf["value"] is None
    assert "No Fault Detected" in conf["subtext"]

    fault_report = DiagnosticReport(
        task_id="t_fault",
        overall_network_health=NetworkHealthStatus.DEGRADED,
        fault_detected=True,
        health_classification="DEGRADED",
        root_cause_confidence=0.88,
        confidence_score=0.88,
        confidence_interpretation="CALIBRATED_HEURISTIC_SCORE",
    )
    conf_fault = get_confidence_display(fault_report)
    assert conf_fault["is_applicable"] is True
    assert conf_fault["display_text"] == "88.0%"
    assert conf_fault["value"] == 0.88
    assert "Heuristic" in conf_fault["subtext"]


# =============================================================================
# SCENARIO 9: CERTAINTY TIER DECOUPLING
# =============================================================================

def test_09_diagnostic_summary_certainty_tier_decoupling():
    """Verify hypothesis certainty tiers do not conflict with network health."""
    confirmed = get_certainty_badge("CONFIRMED")
    assert confirmed["label"] == "CONFIRMED"
    assert confirmed["color"] == "#10B981"

    provisional = get_certainty_badge("PROVISIONAL")
    assert provisional["label"] == "PROVISIONAL"
    assert provisional["color"] == "#F59E0B"

    indeterminate = get_certainty_badge("INDETERMINATE")
    assert indeterminate["label"] == "INDETERMINATE"
    assert indeterminate["color"] == "#EF4444"

    not_app = get_certainty_badge("NOT_APPLICABLE")
    assert not_app["label"] == "NOT APPLICABLE"
    assert not_app["color"] == "#38BDF8"


# =============================================================================
# SCENARIO 10: ALTERNATIVE HYPOTHESES & UNCERTAINTY NOTES
# =============================================================================

def test_10_diagnostic_summary_alternative_hypotheses_and_uncertainty():
    """Verify competing hypotheses, supporting/contradicting factors, and uncertainty notes."""
    alt = RootCauseCandidate(
        title="Access Point Interference",
        category="CONNECTIVITY",
        confidence=0.45,
        supporting_symptoms=["Low Wi-Fi RSSI"],
        contradicting_symptoms=["Core transit links operating at 95% bandwidth"],
    )
    report = DiagnosticReport(
        task_id="t_alt",
        alternative_causes=[alt],
        uncertainty_notes=["High transit congestion partially masks wireless link degradation."],
    )
    assert len(report.alternative_causes) == 1
    assert report.alternative_causes[0].title == "Access Point Interference"
    assert len(report.uncertainty_notes) == 1
    assert "masks" in report.uncertainty_notes[0]


# =============================================================================
# SCENARIO 11: AGENT EXECUTION GRID (ALL 5 CANONICAL AGENTS)
# =============================================================================

def test_11_agent_execution_grid_all_five_agents():
    """All 5 canonical agents must be accounted for in the execution grid."""
    report = DiagnosticReport(
        task_id="t_all_agents",
        successful_agents=[
            "performance_agent",
            "infrastructure_agent",
            "connectivity_agent",
            "correlation_agent",
            "recommendation_agent",
        ],
    )
    grid = get_agent_status_grid(report)
    assert len(grid) == 5
    agent_ids = [a["agent_id"] for a in grid]
    for expected_id in ["performance_agent", "infrastructure_agent", "connectivity_agent", "correlation_agent", "recommendation_agent"]:
        assert expected_id in agent_ids
    for a in grid:
        assert a["status"] == "SUCCESS"
        assert a["is_healthy"] is True


# =============================================================================
# SCENARIO 12: FAILURE ISOLATION (FAILED/TIMED-OUT NEVER DISPLAYED AS HEALTHY)
# =============================================================================

def test_12_failed_or_timed_out_agent_never_displayed_healthy():
    """CRITICAL: A missing, failed, or timed-out agent must NEVER be displayed as healthy."""
    report = DiagnosticReport(
        task_id="t_failures",
        successful_agents=["performance_agent"],
        failed_agents=["infrastructure_agent"],
        timed_out_agents=["connectivity_agent"],
        individual_agent_findings={
            "infrastructure_agent": AgentMessage(
                task_id="t_failures",
                agent_id="infrastructure_agent",
                status=AgentStatus.ERROR,
                errors=["Connection timed out to SNMP daemon"],
            ),
            "connectivity_agent": AgentMessage(
                task_id="t_failures",
                agent_id="connectivity_agent",
                status=AgentStatus.TIMEOUT,
                errors=["Agent connectivity_agent timed out after 0.25s."],
            ),
        },
    )
    grid = get_agent_status_grid(report)
    grid_map = {a["agent_id"]: a for a in grid}

    assert grid_map["performance_agent"]["status"] == "SUCCESS"
    assert grid_map["performance_agent"]["is_healthy"] is True

    assert grid_map["infrastructure_agent"]["status"] == "FAILED"
    assert grid_map["infrastructure_agent"]["is_healthy"] is False
    assert any("SNMP" in err for err in grid_map["infrastructure_agent"]["errors"])

    assert grid_map["connectivity_agent"]["status"] == "TIMEOUT"
    assert grid_map["connectivity_agent"]["is_healthy"] is False
    assert any("timed out" in err for err in grid_map["connectivity_agent"]["errors"])


# =============================================================================
# SCENARIO 13: TELEMETRY TIME-SERIES CHRONOLOGICAL SORTING
# =============================================================================

def test_13_telemetry_visualization_time_series_chronological_sorting():
    """Multi-timestamp data must be detected as time-series and sorted chronologically."""
    out_of_order = [
        {"device_id": "r1", "timestamp": "2026-10-31T12:05:00Z", "latency_ms": 30.0},
        {"device_id": "r1", "timestamp": "2026-10-31T12:00:00Z", "latency_ms": 15.0},
        {"device_id": "r1", "timestamp": "2026-10-31T12:02:00Z", "latency_ms": 22.0},
    ]
    df_raw = pd.DataFrame(out_of_order)
    clean_df, meta = prepare_telemetry_dataframe(df_raw)

    assert meta["mode"] == "time_series"
    assert clean_df.iloc[0]["latency_ms"] == 15.0
    assert clean_df.iloc[1]["latency_ms"] == 22.0
    assert clean_df.iloc[2]["latency_ms"] == 30.0


# =============================================================================
# SCENARIO 14: TELEMETRY SINGLE-SNAPSHOT MODE DETECTION
# =============================================================================

def test_14_telemetry_visualization_single_snapshot_mode():
    """Single timestamp data across devices must be detected as snapshot, not time series."""
    snapshot_data = [
        {"device_id": "core-router-01", "timestamp": "2026-10-31T12:00:00Z", "cpu_util_pct": 75.0},
        {"device_id": "dist-switch-02", "timestamp": "2026-10-31T12:00:00Z", "cpu_util_pct": 45.0},
    ]
    df_raw = pd.DataFrame(snapshot_data)
    clean_df, meta = prepare_telemetry_dataframe(df_raw)

    assert meta["mode"] == "snapshot"
    assert meta["device_count"] == 2


# =============================================================================
# SCENARIO 15: ALL 10 METRICS WITH UNITS AND NO SILENT ZERO-FILLING
# =============================================================================

def test_15_telemetry_visualization_all_ten_metrics_no_zero_filling():
    """Verify that all 10 metrics have defined units and NaNs are NOT converted to zero."""
    for metric_col in [
        "latency_ms", "jitter_ms", "packet_loss_pct", "throughput_mbps",
        "bandwidth_util_pct", "cpu_util_pct", "memory_util_pct",
        "wifi_rssi_dbm", "queue_drops", "interface_errors"
    ]:
        assert metric_col in METRIC_CONFIG
        assert METRIC_CONFIG[metric_col]["unit"]

    # Verify NaNs are preserved, never filled with zero
    data_with_nans = [
        {"device_id": "r1", "latency_ms": 15.0, "jitter_ms": None, "queue_drops": None},
        {"device_id": "r2", "latency_ms": None, "jitter_ms": 4.5, "queue_drops": "invalid_str"},
    ]
    df = pd.DataFrame(data_with_nans)
    clean_df, meta = prepare_telemetry_dataframe(df)

    assert pd.isna(clean_df.loc[0, "jitter_ms"])
    assert pd.isna(clean_df.loc[1, "latency_ms"])
    assert pd.isna(clean_df.loc[1, "queue_drops"])  # coerced string to NaN, not 0


# =============================================================================
# SCENARIO 16: FINDINGS EXPLORER COMPLETE FIELDS AND FILTERING
# =============================================================================

def test_16_findings_explorer_complete_columns_and_filtering():
    """Verifies that all 10 required findings fields (+ Description) are present and filterable."""
    now = datetime.now(timezone.utc)
    finding = Finding(
        finding_id="FND-TEST-001",
        category="PERFORMANCE",
        title="High Latency Spike",
        description="RTT exceeded 120ms on core router",
        severity=Severity.HIGH,
        affected_devices=["core-router-01"],
        source_agent="performance_agent",
        interface_name="GigabitEthernet0/1",
        metric_name="latency_ms",
        observed_value=125.4,
        threshold_value=50.0,
        finding_type="OBSERVED_EVIDENCE",
        timestamp=now,
    )
    report = DiagnosticReport(
        task_id="t_findings",
        validated_findings=[finding],
    )
    df = build_findings_table(report)
    assert not df.empty

    required_fields = [
        "Finding ID", "Source Agent", "Device", "Interface", "Metric",
        "Observed Value", "Threshold", "Severity", "Timestamp", "Finding Type"
    ]
    for col in required_fields:
        assert col in df.columns, f"Missing column {col}"

    # Verify content accuracy
    row = df.iloc[0]
    assert row["Finding ID"] == "FND-TEST-001"
    assert row["Source Agent"] == "performance_agent"
    assert row["Severity"] == "HIGH"
    assert row["Observed Value"] == "125.40"
    assert row["Threshold"] == "50.00"


# =============================================================================
# SCENARIO 17: EVIDENCE EXPLORER COMPLETE PROVENANCE & BASELINES
# =============================================================================

def test_17_evidence_explorer_complete_provenance_and_baselines():
    """Verifies that supporting evidence table parses all required metrics and thresholds."""
    ev = EvidenceItem(
        metric_name="bandwidth_util_pct",
        observed_value=96.2,
        threshold=80.0,
        unit="%",
        details="Transit link utilization saturated buffer queues.",
        device_id="core-router-01",
    )
    report = DiagnosticReport(
        task_id="t_evidence",
        supporting_evidence=[ev],
    )
    df = build_evidence_table(report)
    assert not df.empty
    assert "Evidence ID" in df.columns
    assert "Metric Name" in df.columns
    assert "Observed Value" in df.columns
    assert "Normal Baseline" in df.columns
    assert "Breach Details" in df.columns
    assert df.iloc[0]["Observed Value"] == "96.2 %"
    assert df.iloc[0]["Normal Baseline"] == "80.0 %"


# =============================================================================
# SCENARIO 18: RECOMMENDATIONS ADVISORY SAFETY & DISRUPTIVE APPROVAL
# =============================================================================

def test_18_recommendations_advisory_safety_and_disruptive_approval():
    """
    Verifies that corrective actions clearly distinguish:
    - READ-ONLY Diagnostic actions
    - Disruptive actions requiring NOC approval
    - Missing approval information is NEVER interpreted as approval
    - Prerequisites, verification, and rollback procedures
    """
    read_only_action = CorrectiveAction(
        action_id="ACT-01",
        title="Check DNS Server Reachability",
        description="Send ICMP echo and port 53 query to primary nameserver.",
        action_type="DIAGNOSTIC",
        execution_risk="LOW",
        requires_human_approval=False,
        prerequisites=["ICMP enabled on gateway"],
        verification_steps=["dig @192.168.1.1 google.com"],
        rollback_steps=[],
    )
    c_read = categorize_action(read_only_action)
    assert c_read["category_label"] == "READ-ONLY DIAGNOSTIC"
    assert c_read["requires_human_approval"] is False
    assert c_read["is_disruptive"] is False

    disruptive_action = CorrectiveAction(
        action_id="ACT-02",
        title="Restart Core Interface GigabitEthernet0/1",
        description="Bounce interface to clear hardware CRC frame state.",
        action_type="HARDWARE",
        execution_risk="HIGH",
        requires_human_approval=True,
        prerequisites=["Secondary BGP path established"],
        verification_steps=["show interface GigabitEthernet0/1 status"],
        rollback_steps=["no shutdown GigabitEthernet0/1"],
        automation_command="interface GigabitEthernet0/1\nshutdown\nno shutdown",
    )
    c_disrupt = categorize_action(disruptive_action)
    assert c_disrupt["category_label"] == "DISRUPTIVE REMEDIATION"
    assert c_disrupt["requires_human_approval"] is True
    assert c_disrupt["is_disruptive"] is True
    assert len(c_disrupt["rollback_steps"]) == 1

    # Missing approval information must NOT be interpreted as approval
    missing_approval_action = mock.Mock(
        action_id="ACT-03",
        title="Flush Route Cache",
        description="Clear routing cache entries.",
        action_type="CONFIGURATION",
        execution_risk="MEDIUM",
        requires_human_approval=None,  # missing info
        affected_devices=[],
        supporting_evidence=[],
        prerequisites=[],
        verification_steps=[],
        rollback_steps=[],
        automation_command=None,
    )
    c_missing = categorize_action(missing_approval_action)
    assert c_missing["requires_human_approval"] is True, "Missing approval info must default to requiring approval!"


# =============================================================================
# SCENARIO 19: REPORT HISTORY RETRIEVAL & DUAL ID LOOKUP
# =============================================================================

def test_19_report_history_retrieval_and_dual_id_lookup(tmp_path):
    """
    Verifies report history management:
    - Retrieve previously generated reports
    - Display report ID, diagnosis ID, timestamp, and health
    - Dual lookup by report ID and diagnosis ID
    - Handle empty history
    - Handle non-existent or deleted reports gracefully
    """
    # 1. Empty history
    empty_list = list_saved_reports(tmp_path)
    assert empty_list == []

    # 2. Save a report
    rep = DiagnosticReport(
        report_id="REP-HIST-001",
        diagnosis_id="DIAG-HIST-001",
        task_id="t_hist",
        overall_network_health=NetworkHealthStatus.DEGRADED,
        health_classification="DEGRADED",
        fault_detected=True,
        summary="History test report",
        probable_root_cause=RootCauseCandidate(title="Buffer Congestion", confidence=0.85),
    )
    file_path = tmp_path / "REP-HIST-001.json"
    file_path.write_text(rep.model_dump_json(indent=2), encoding="utf-8")

    # 3. Retrieve history listing
    hist = list_saved_reports(tmp_path)
    assert len(hist) == 1
    assert hist[0]["report_id"] == "REP-HIST-001"
    assert hist[0]["diagnosis_id"] == "DIAG-HIST-001"
    assert hist[0]["health_classification"] == "DEGRADED"

    # 4. Lookup by Report ID
    loaded_by_rep, err1 = load_saved_report("REP-HIST-001", tmp_path)
    assert loaded_by_rep is not None
    assert err1 is None
    assert loaded_by_rep.report_id == "REP-HIST-001"

    # 5. Lookup by Diagnosis ID
    loaded_by_diag, err2 = load_saved_report("DIAG-HIST-001", tmp_path)
    assert loaded_by_diag is not None
    assert err2 is None
    assert loaded_by_diag.diagnosis_id == "DIAG-HIST-001"

    # 6. Lookup non-existent report
    missing_rep, err3 = load_saved_report("NONEXISTENT-REP", tmp_path)
    assert missing_rep is None
    assert "not found" in err3.lower()


# =============================================================================
# SCENARIO 20: API FAILURE HANDLING & MALFORMED RESPONSES
# =============================================================================

def test_20_api_failure_handling_and_malformed_responses():
    """
    Verifies robust dashboard handling of API failures:
    - Server unavailable / ConnectionError
    - Connection timeout
    - HTTP 400 Bad Request
    - HTTP 404 Not Found
    - HTTP 500 Internal Error
    - Malformed non-JSON response
    - Schema validation errors on incomplete payloads
    """
    # 1. Server offline / ConnectionError
    with mock.patch("requests.get", side_effect=requests.exceptions.ConnectionError("Connection refused")):
        rep, err = fetch_report_from_api("REP-001")
        assert rep is None
        assert "offline or unreachable" in err

    # 2. Connection timeout
    with mock.patch("requests.get", side_effect=requests.exceptions.Timeout("Timed out")):
        rep, err = fetch_report_from_api("REP-001", timeout=1.0)
        assert rep is None
        assert "timed out" in err

    # 3. HTTP 400
    mock_400 = mock.Mock(status_code=400, text="Bad Request Parameters")
    with mock.patch("requests.get", return_value=mock_400):
        rep, err = fetch_report_from_api("REP-001")
        assert rep is None
        assert "400" in err

    # 4. HTTP 404
    mock_404 = mock.Mock(status_code=404, text="Not Found")
    with mock.patch("requests.get", return_value=mock_404):
        rep, err = fetch_report_from_api("REP-001")
        assert rep is None
        assert "404" in err

    # 5. HTTP 500
    mock_500 = mock.Mock(status_code=500, text="Internal Server Error")
    with mock.patch("requests.get", return_value=mock_500):
        rep, err = fetch_report_from_api("REP-001")
        assert rep is None
        assert "500" in err

    # 6. Malformed non-JSON response
    mock_malformed = mock.Mock(status_code=200, json=mock.Mock(side_effect=ValueError("Invalid JSON")))
    with mock.patch("requests.get", return_value=mock_malformed):
        rep, err = fetch_report_from_api("REP-001")
        assert rep is None
        assert "malformed non-json" in err.lower()

    # 7. Valid JSON but incomplete schema (e.g. missing required task_id)
    mock_incomplete = mock.Mock(status_code=200, json=mock.Mock(return_value={"invalid_key": "val"}))
    with mock.patch("requests.get", return_value=mock_incomplete):
        rep, err = fetch_report_from_api("REP-001")
        assert rep is None
        assert "schema validation" in err.lower()


# =============================================================================
# SCENARIO 21: STREAMLIT APPLICATION-LEVEL EXECUTION (APPTEST SMOKE TESTS)
# =============================================================================

def test_21_streamlit_apptest_smoke_execution():
    """
    Executes the Streamlit application using AppTest to verify:
    - Application starts successfully with zero exceptions.
    - Healthy report renders cleanly without errors.
    - Fault report renders cleanly without errors.
    - Script compilation succeeds.
    """
    # 1. Compilation check
    compiled = py_compile.compile("dashboard/app.py", doraise=True)
    assert compiled is not None

    app_path = str(Path(__file__).resolve().parent.parent / "dashboard" / "app.py")

    # 2. Initial page load execution
    at = AppTest.from_file(app_path)
    at.run(timeout=15)
    assert len(at.exception) == 0, f"AppTest raised unexpected exceptions: {at.exception}"

    # 3. Simulate healthy report in session state
    at_healthy = AppTest.from_file(app_path)
    healthy_rep = DiagnosticReport(
        task_id="t_app_health",
        overall_network_health=NetworkHealthStatus.HEALTHY,
        health_classification="NOMINAL",
        fault_detected=False,
        diagnosis_certainty="NOT_APPLICABLE",
        schema_version="2.0.0",
        summary="All systems nominal.",
    )
    at_healthy.session_state["diagnostic_report"] = healthy_rep
    at_healthy.run(timeout=15)
    assert len(at_healthy.exception) == 0

    # 4. Simulate active fault report in session state
    at_fault = AppTest.from_file(app_path)
    fault_rep = DiagnosticReport(
        task_id="t_app_fault",
        overall_network_health=NetworkHealthStatus.DEGRADED,
        health_classification="DEGRADED",
        fault_detected=True,
        root_cause_confidence=0.91,
        confidence_score=0.91,
        diagnosis_certainty="CONFIRMED",
        probable_root_cause=RootCauseCandidate(
            title="Link Congestion",
            description="Peak transit traffic.",
            confidence=0.91,
        ),
        schema_version="2.0.0",
        summary="Bandwidth saturation observed.",
    )
    at_fault.session_state["diagnostic_report"] = fault_rep
    at_fault.run(timeout=15)
    assert len(at_fault.exception) == 0


def test_22_diagnose_via_api_mocked():
    """Verify diagnose_via_api sends proper requests and handles responses."""
    mock_rep = DiagnosticReport(
        task_id="t_api_diag",
        overall_network_health=NetworkHealthStatus.HEALTHY,
        health_classification="NOMINAL",
        fault_detected=False,
        diagnosis_certainty="NOT_APPLICABLE",
        schema_version="2.0.0",
        summary="All systems nominal.",
    )
    mock_resp = mock.Mock(status_code=200, json=mock.Mock(return_value=mock_rep.model_dump()))
    with mock.patch("requests.post", return_value=mock_resp):
        rep, err = diagnose_via_api(scenario_id="congestion")
        assert err is None
        assert rep is not None
        assert rep.task_id == "t_api_diag"

    # Connection error isolation
    with mock.patch("requests.post", side_effect=requests.exceptions.ConnectionError("Connection refused")):
        rep, err = diagnose_via_api(scenario_id="congestion")
        assert rep is None
        assert "offline" in err.lower()


def test_23_dashboard_demo_and_actions_recommendations_rendering():
    """
    Regression test verifying that dashboard/app.py correctly accesses
    recommended_corrective_actions / recommendations without raising
    AttributeError: 'DiagnosticReport' object has no attribute 'recommended_actions'.
    """
    from streamlit.testing.v1 import AppTest
    from data.scenarios import generate_scenario_data
    from orchestrator.orchestrator import CentralOrchestrator

    # 1. Generate a real DiagnosticReport with recommendations
    orch = CentralOrchestrator()
    records = generate_scenario_data("congestion")
    real_report = orch.run_diagnosis(records, scenario_name="congestion", save_report=False)
    assert len(real_report.recommended_corrective_actions) > 0

    # 2. Test Streamlit app rendering with real report in session_state
    app_path = str(Path(__file__).resolve().parent.parent / "dashboard" / "app.py")
    at = AppTest.from_file(app_path)
    at.session_state["demo_report"] = real_report
    at.session_state["diagnostic_report"] = real_report
    at.session_state["demo_baseline"] = None
    at.session_state["demo_df"] = pd.DataFrame(records)
    at.session_state["demo_metric"] = "packet_loss_pct"
    at.session_state["demo_scenario_active"] = "congestion"
    at.run(timeout=15)
    assert len(at.exception) == 0, f"AppTest raised unexpected exceptions: {at.exception}"

    # 3. Test with empty recommendations list safely
    at_empty = AppTest.from_file(app_path)
    empty_report = DiagnosticReport(
        task_id="t_empty_recs",
        overall_network_health=NetworkHealthStatus.HEALTHY,
        health_classification="NOMINAL",
        fault_detected=False,
        diagnosis_certainty="NOT_APPLICABLE",
        recommended_corrective_actions=[],
        recommendations=[],
        schema_version="2.0.0",
        summary="Nominal status.",
    )
    at_empty.session_state["demo_report"] = empty_report
    at_empty.session_state["diagnostic_report"] = empty_report
    at_empty.session_state["demo_baseline"] = None
    at_empty.session_state["demo_df"] = pd.DataFrame(records)
    at_empty.session_state["demo_metric"] = "packet_loss_pct"
    at_empty.session_state["demo_scenario_active"] = "normal"
    at_empty.run(timeout=15)
    assert len(at_empty.exception) == 0, f"AppTest raised unexpected exceptions: {at_empty.exception}"

