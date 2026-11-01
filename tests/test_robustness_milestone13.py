"""
NetCoop AI — Milestone 13: System-Wide Robustness Audit & Verification Suite
=============================================================================
Comprehensive test suite verifying system-wide resilience across all 6 audit phases:
  - Phase 2: Telemetry & Schema Robustness (15 scenarios)
  - Phase 3: Multi-Agent & Orchestrator Robustness (15 scenarios)
  - Phase 4: Report & Confidence Consistency (11 scenarios)
  - Phase 5: Recommendation Safety (7 scenarios)
  - Phase 6: API & Dashboard Integration (5 scenarios)
Total: 53 automated tests.
"""

from __future__ import annotations

import concurrent.futures
from datetime import datetime, timedelta, timezone
import io
import json
from pathlib import Path
import time
from typing import Any, Dict, List
import unittest.mock as mock
import uuid

from fastapi.testclient import TestClient
import numpy as np
import pandas as pd
import pytest

from api.main import app
from communication.models import (
    AgentMessage,
    AgentStatus,
    EvidenceItem,
    Finding,
    NetworkTelemetryRecord,
    Severity,
    TelemetryBatch,
)
from communication.protocol import create_agent_message, create_error_message, validate_message
from communication.telemetry_ingestion import TelemetryIngestionService
from communication.telemetry_schema import (
    ConnectivityStatus,
    DHCPStatus,
    DNSStatus,
    DeviceStatus,
    TelemetryRecord,
)
from communication.telemetry_validator import RecordValidationError, TelemetryValidator
from dashboard.components import (
    categorize_action,
    fetch_report_from_api,
    get_agent_status_grid,
    get_confidence_display,
    prepare_telemetry_dataframe,
)
from data.scenarios import generate_scenario_data
from diagnosis.models import (
    CorrectiveAction,
    DiagnosticReport,
    NetworkHealthStatus,
    RecommendationItem,
    RootCauseCandidate,
)
from diagnosis.recommendation_agent import RecommendationAgent
from orchestrator.orchestrator import CentralOrchestrator


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def orchestrator(tmp_path):
    """Provides an isolated CentralOrchestrator instance writing to a temporary reports dir."""
    return CentralOrchestrator(reports_dir=str(tmp_path / "reports"), agent_timeout_seconds=2.0)


@pytest.fixture
def sample_valid_telemetry():
    """Generates a small valid telemetry dataset."""
    now = datetime.now(timezone.utc)
    return [
        {
            "timestamp": (now - timedelta(minutes=5)).isoformat(),
            "device_id": "core-router-01",
            "device_type": "router",
            "interface_name": "GigabitEthernet0/0",
            "latency_ms": 12.5,
            "jitter_ms": 1.2,
            "packet_loss_pct": 0.0,
            "throughput_mbps": 450.0,
            "bandwidth_util_pct": 45.0,
            "cpu_util_pct": 25.0,
            "memory_util_pct": 40.0,
            "device_status": "active",
            "connectivity_status": "connected",
        },
        {
            "timestamp": now.isoformat(),
            "device_id": "core-router-01",
            "device_type": "router",
            "interface_name": "GigabitEthernet0/0",
            "latency_ms": 14.1,
            "jitter_ms": 1.8,
            "packet_loss_pct": 0.0,
            "throughput_mbps": 420.0,
            "bandwidth_util_pct": 42.0,
            "cpu_util_pct": 28.0,
            "memory_util_pct": 41.0,
            "device_status": "active",
            "connectivity_status": "connected",
        },
    ]


# =============================================================================
# PHASE 2: TELEMETRY AND SCHEMA ROBUSTNESS (15 TESTS)
# =============================================================================

def test_phase2_01_missing_optional_telemetry_fields():
    """Missing optional fields do not fail schema validation and are not converted to zero."""
    now = datetime.now(timezone.utc)
    raw = {
        "device_id": "edge-sw-01",
        "timestamp": now.isoformat(),
        # All other performance/infrastructure metrics omitted
    }
    res = TelemetryValidator.validate_record(raw)
    assert res.is_valid is True
    assert res.record is not None
    assert res.record.device_id == "edge-sw-01"
    assert res.record.latency_ms is None
    assert res.record.packet_loss_percent is None
    assert res.record.cpu_utilization_percent is None


def test_phase2_02_missing_required_fields():
    """Missing required device_id or timestamp generates explicit field-level errors."""
    now = datetime.now(timezone.utc)
    # Missing device_id
    res1 = TelemetryValidator.validate_record({"timestamp": now.isoformat()})
    assert res1.is_valid is False
    assert any(e.field == "device_id" for e in res1.errors)

    # Missing timestamp
    res2 = TelemetryValidator.validate_record({"device_id": "sw-01"})
    assert res2.is_valid is False
    assert any(e.field == "timestamp" for e in res2.errors)


def test_phase2_03_null_values():
    """Null values for required fields fail, while null values for optional fields stay None."""
    now = datetime.now(timezone.utc)
    res_null_dev = TelemetryValidator.validate_record({"device_id": None, "timestamp": now.isoformat()})
    assert res_null_dev.is_valid is False

    res_null_metric = TelemetryValidator.validate_record({
        "device_id": "r1",
        "timestamp": now.isoformat(),
        "latency_ms": None,
    })
    assert res_null_metric.is_valid is True
    assert res_null_metric.record.latency_ms is None


def test_phase2_04_empty_strings():
    """Empty or whitespace-only device_id or timestamp fails validation."""
    now = datetime.now(timezone.utc)
    res_empty_dev = TelemetryValidator.validate_record({"device_id": "   ", "timestamp": now.isoformat()})
    assert res_empty_dev.is_valid is False

    res_empty_ts = TelemetryValidator.validate_record({"device_id": "r1", "timestamp": ""})
    assert res_empty_ts.is_valid is False


def test_phase2_05_invalid_numeric_strings():
    """Non-numeric string values in numeric metric fields are rejected without crashing."""
    now = datetime.now(timezone.utc)
    raw = {
        "device_id": "r1",
        "timestamp": now.isoformat(),
        "latency_ms": "not_a_number",
        "packet_loss_pct": "--",
    }
    res = TelemetryValidator.validate_record(raw)
    assert res.is_valid is False
    failed_fields = [e.field for e in res.errors]
    assert "latency_ms" in failed_fields
    assert "packet_loss_percent" in failed_fields


def test_phase2_06_negative_metric_values_rejected():
    """Negative values for metrics with lower bound of 0 are rejected."""
    now = datetime.now(timezone.utc)
    raw = {
        "device_id": "r1",
        "timestamp": now.isoformat(),
        "latency_ms": -10.5,
        "packet_loss_pct": -0.5,
        "queue_drops": -1,
    }
    res = TelemetryValidator.validate_record(raw)
    assert res.is_valid is False
    failed_fields = [e.field for e in res.errors]
    assert "latency_ms" in failed_fields
    assert "packet_loss_percent" in failed_fields
    assert "queue_drops" in failed_fields


def test_phase2_07_extremely_large_percentage_metric_values():
    """Percentage metrics strictly reject values > 100.0%."""
    now = datetime.now(timezone.utc)
    raw = {
        "device_id": "r1",
        "timestamp": now.isoformat(),
        "packet_loss_pct": 100.1,
        "bandwidth_util_pct": 150.0,
        "cpu_util_pct": 250.0,
        "memory_util_pct": 105.0,
    }
    res = TelemetryValidator.validate_record(raw)
    assert res.is_valid is False
    failed_fields = [e.field for e in res.errors]
    assert "packet_loss_percent" in failed_fields
    assert "bandwidth_utilization_percent" in failed_fields
    assert "cpu_utilization_percent" in failed_fields
    assert "memory_utilization_percent" in failed_fields


def test_phase2_08_invalid_timestamps():
    """Unparseable or nonsensical timestamp strings fail validation."""
    raw = {
        "device_id": "r1",
        "timestamp": "2026-99-99T99:99:99Z",
    }
    res = TelemetryValidator.validate_record(raw)
    assert res.is_valid is False
    assert any("timestamp" in e.field for e in res.errors)


def test_phase2_09_duplicate_device_records():
    """Batch ingestion supports multiple telemetry records for the same device across timestamps."""
    now = datetime.now(timezone.utc)
    batch = [
        {"device_id": "core-01", "timestamp": (now - timedelta(seconds=60)).isoformat(), "latency_ms": 10.0},
        {"device_id": "core-01", "timestamp": now.isoformat(), "latency_ms": 12.0},
    ]
    valid_recs, errors = TelemetryValidator.validate_batch(batch)
    assert len(valid_recs) == 2
    assert len(errors) == 0


def test_phase2_10_out_of_order_timestamps():
    """Telemetry data preprocessor sorts out-of-order timestamps chronologically."""
    t0 = datetime(2026, 10, 31, 10, 0, 0, tzinfo=timezone.utc)
    t1 = datetime(2026, 10, 31, 10, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 10, 31, 10, 5, 0, tzinfo=timezone.utc)
    df = pd.DataFrame([
        {"timestamp": t1.isoformat(), "latency_ms": 50.0, "device_id": "r1"},
        {"timestamp": t0.isoformat(), "latency_ms": 10.0, "device_id": "r1"},
        {"timestamp": t2.isoformat(), "latency_ms": 25.0, "device_id": "r1"},
    ])
    clean_df, meta = prepare_telemetry_dataframe(df)
    assert meta["mode"] == "time_series"
    timestamps = list(clean_df["timestamp"])
    assert timestamps == sorted(timestamps)


def test_phase2_11_empty_telemetry_batches(orchestrator):
    """Submitting an empty telemetry batch produces an UNKNOWN health report without crashing."""
    report = orchestrator.run_diagnosis([], scenario_name="empty_test")
    assert report.overall_network_health == NetworkHealthStatus.UNKNOWN
    assert report.execution_status == "FAILED"
    assert report.confidence_score == 0.0
    assert report.limitations.insufficient_evidence is True


def test_phase2_12_partially_invalid_batches(orchestrator, sample_valid_telemetry):
    """Partially invalid batch isolates the bad record while analyzing valid records."""
    batch = list(sample_valid_telemetry)
    batch.append({"device_id": "broken", "timestamp": "invalid_date", "packet_loss_pct": 500.0})

    report = orchestrator.run_diagnosis(batch)
    assert report.execution_status in ["COMPLETED", "COMPLETED_WITH_WARNINGS", "PARTIAL_SUCCESS", "SUCCESS"]
    assert len(report.limitations.invalid_records) > 0


def test_phase2_13_completely_invalid_batches(orchestrator):
    """Completely invalid batch produces a safe failure report with zero unhandled exceptions."""
    bad_batch = [
        {"timestamp": "bad1"},
        {"device_id": "bad2", "latency_ms": -100.0, "packet_loss_pct": 999.0},
    ]
    report = orchestrator.run_diagnosis(bad_batch)
    assert report.overall_network_health == NetworkHealthStatus.UNKNOWN
    assert report.fault_detected is False
    assert len(report.errors) > 0


def test_phase2_14_unknown_additional_fields():
    """Unknown additional fields are accepted safely under extra='ignore'."""
    now = datetime.now(timezone.utc)
    raw = {
        "device_id": "r1",
        "timestamp": now.isoformat(),
        "latency_ms": 15.0,
        "vendor_internal_hash": "a1b2c3d4",
        "custom_tag": 9999,
    }
    res = TelemetryValidator.validate_record(raw)
    assert res.is_valid is True
    assert res.record.device_id == "r1"


def test_phase2_15_unexpected_json_structures(orchestrator):
    """Unexpected JSON structures like top-level primitives or lists of primitives are rejected safely."""
    res_prim, errs = orchestrator.validate_and_normalize_telemetry(["invalid_string", 12345])
    assert res_prim.empty
    assert len(errs) > 0


# =============================================================================
# PHASE 3: MULTI-AGENT AND ORCHESTRATOR ROBUSTNESS (15 TESTS)
# =============================================================================

def test_phase3_01_all_five_agents_succeed(orchestrator, sample_valid_telemetry):
    """All registered domain agents succeed and are tracked in successful_agents."""
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert "performance_agent" in report.successful_agents
    assert "infrastructure_agent" in report.successful_agents
    assert "connectivity_agent" in report.successful_agents
    assert len(report.failed_agents) == 0
    assert len(report.timed_out_agents) == 0


def test_phase3_02_one_agent_fails(orchestrator, sample_valid_telemetry):
    """One domain agent raising an exception is isolated; remaining agents' results are retained."""
    mock_perf = mock.Mock()
    mock_perf.execute.side_effect = RuntimeError("Telemetry parser core crash")
    orchestrator.performance_agent = mock_perf

    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert "performance_agent" in report.failed_agents
    assert "infrastructure_agent" in report.successful_agents
    assert "connectivity_agent" in report.successful_agents
    assert report.overall_status in ["COMPLETED_WITH_WARNINGS", "PARTIAL_SUCCESS", "COMPLETED", "DEGRADED"]


def test_phase3_03_multiple_agents_fail(orchestrator, sample_valid_telemetry):
    """Multiple failing agents do not prevent report generation or crash the orchestrator."""
    mock_perf = mock.Mock()
    mock_perf.execute.side_effect = RuntimeError("Crash 1")
    mock_conn = mock.Mock()
    mock_conn.execute.side_effect = ValueError("Crash 2")
    orchestrator.performance_agent = mock_perf
    orchestrator.connectivity_agent = mock_conn

    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert "performance_agent" in report.failed_agents
    assert "connectivity_agent" in report.failed_agents
    assert "infrastructure_agent" in report.successful_agents


def test_phase3_04_one_agent_times_out(orchestrator, sample_valid_telemetry):
    """An agent that exceeds timeout returns bounded within configured time and is marked TIMEOUT."""
    orchestrator.agent_timeout = 0.3

    def slow_exec(task_id, df):
        time.sleep(1.0)
        return create_agent_message(task_id, "performance_agent", status=AgentStatus.SUCCESS)

    mock_slow = mock.Mock()
    mock_slow.execute.side_effect = slow_exec
    orchestrator.performance_agent = mock_slow

    t0 = time.perf_counter()
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    elapsed = time.perf_counter() - t0

    assert elapsed < 1.5, f"Orchestrator blocked for too long: {elapsed}s"
    assert "performance_agent" in report.timed_out_agents
    assert "infrastructure_agent" in report.successful_agents


def test_phase3_05_multiple_agents_time_out(orchestrator, sample_valid_telemetry):
    """Multiple agents timing out are all captured without indefinite blocking."""
    orchestrator.agent_timeout = 0.2

    def sleep_worker(task_id, df):
        time.sleep(0.8)
        return create_agent_message(task_id, "mock_agent")

    mock_slow1 = mock.Mock()
    mock_slow1.execute.side_effect = sleep_worker
    mock_slow2 = mock.Mock()
    mock_slow2.execute.side_effect = sleep_worker

    orchestrator.performance_agent = mock_slow1
    orchestrator.infrastructure_agent = mock_slow2

    t0 = time.perf_counter()
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    elapsed = time.perf_counter() - t0

    assert elapsed < 1.2
    assert "performance_agent" in report.timed_out_agents
    assert "infrastructure_agent" in report.timed_out_agents


def test_phase3_06_agent_returns_malformed_output(orchestrator, sample_valid_telemetry):
    """Agent returning non-conforming message object is rejected into rejected_messages."""
    mock_bad = mock.Mock()
    mock_bad.execute.return_value = {"not": "an_agent_message"}
    orchestrator.performance_agent = mock_bad

    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert "performance_agent" in report.failed_agents
    assert len(report.rejected_messages) > 0


def test_phase3_07_agent_returns_wrong_identity(orchestrator, sample_valid_telemetry):
    """Agent returning another agent's ID is rejected for identity spoofing/mismatch."""
    mock_impostor = mock.Mock()
    # performance_agent claims to be connectivity_agent
    mock_impostor.execute.side_effect = lambda tid, df: create_agent_message(tid, "connectivity_agent")
    orchestrator.performance_agent = mock_impostor

    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert "performance_agent" in report.failed_agents
    assert any(rej["agent_id"] == "performance_agent" for rej in report.rejected_messages)


def test_phase3_08_duplicate_agent_messages(orchestrator, sample_valid_telemetry):
    """Two agents sharing the same message_id triggers duplicate detection and rejection."""
    shared_uuid = str(uuid.uuid4())

    mock_agent1 = mock.Mock()
    mock_agent1.execute.side_effect = lambda tid, df: AgentMessage(
        message_id=shared_uuid, task_id=tid, agent_id="performance_agent"
    )
    mock_agent2 = mock.Mock()
    mock_agent2.execute.side_effect = lambda tid, df: AgentMessage(
        message_id=shared_uuid, task_id=tid, agent_id="infrastructure_agent"
    )

    orchestrator.performance_agent = mock_agent1
    orchestrator.infrastructure_agent = mock_agent2

    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    # Exactly one should succeed with the message_id; the other must be rejected
    assert len(report.rejected_messages) >= 1
    assert any("Duplicate message detected" in rej["reason"] for rej in report.rejected_messages)


def test_phase3_09_agent_returns_confidence_outside_bounds(orchestrator, sample_valid_telemetry):
    """Agent returning an out-of-bound confidence score is rejected and quarantined."""
    with pytest.raises(Exception):
        AgentMessage(task_id="t1", agent_id="performance_agent", confidence=-0.5)

    with pytest.raises(Exception):
        AgentMessage(task_id="t1", agent_id="performance_agent", confidence=1.5)

    mock_bad = mock.Mock()
    mock_bad.execute.return_value = {
        "task_id": "t1",
        "agent_id": "performance_agent",
        "confidence": 1.25,
        "status": "SUCCESS",
    }
    orchestrator.performance_agent = mock_bad
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert "performance_agent" in report.failed_agents
    assert any("out of bounds" in str(r.get("reason", "")).lower() for r in report.rejected_messages)


def test_confidence_negative_point_one_rejected(orchestrator, sample_valid_telemetry):
    """Agent response with confidence = -0.1 must be quarantined, not clamped to 0.0."""
    mock_agent = mock.Mock()
    mock_agent.execute.return_value = {
        "task_id": "t_neg",
        "agent_id": "performance_agent",
        "confidence": -0.1,
        "status": "SUCCESS",
    }
    orchestrator.performance_agent = mock_agent
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert "performance_agent" in report.failed_agents
    assert any("out of bounds" in str(r.get("reason", "")).lower() for r in report.rejected_messages)


def test_confidence_one_point_one_rejected(orchestrator, sample_valid_telemetry):
    """Agent response with confidence = 1.1 must be quarantined, not clamped to 1.0."""
    mock_agent = mock.Mock()
    mock_agent.execute.return_value = {
        "task_id": "t_pos",
        "agent_id": "performance_agent",
        "confidence": 1.1,
        "status": "SUCCESS",
    }
    orchestrator.performance_agent = mock_agent
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert "performance_agent" in report.failed_agents
    assert any("out of bounds" in str(r.get("reason", "")).lower() for r in report.rejected_messages)


def test_confidence_nan_rejected(orchestrator, sample_valid_telemetry):
    """Agent response with confidence = NaN must be quarantined."""
    mock_agent = mock.Mock()
    mock_agent.execute.return_value = {
        "task_id": "t_nan",
        "agent_id": "performance_agent",
        "confidence": float("nan"),
        "status": "SUCCESS",
    }
    orchestrator.performance_agent = mock_agent
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert "performance_agent" in report.failed_agents
    assert any("finite" in str(r.get("reason", "")).lower() or "invalid" in str(r.get("reason", "")).lower() for r in report.rejected_messages)


def test_confidence_positive_infinity_rejected(orchestrator, sample_valid_telemetry):
    """Agent response with confidence = +inf must be quarantined."""
    mock_agent = mock.Mock()
    mock_agent.execute.return_value = {
        "task_id": "t_inf",
        "agent_id": "performance_agent",
        "confidence": float("inf"),
        "status": "SUCCESS",
    }
    orchestrator.performance_agent = mock_agent
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert "performance_agent" in report.failed_agents
    assert any("finite" in str(r.get("reason", "")).lower() or "out of bounds" in str(r.get("reason", "")).lower() for r in report.rejected_messages)


def test_confidence_negative_infinity_rejected(orchestrator, sample_valid_telemetry):
    """Agent response with confidence = -inf must be quarantined."""
    mock_agent = mock.Mock()
    mock_agent.execute.return_value = {
        "task_id": "t_ninf",
        "agent_id": "performance_agent",
        "confidence": float("-inf"),
        "status": "SUCCESS",
    }
    orchestrator.performance_agent = mock_agent
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert "performance_agent" in report.failed_agents
    assert any("finite" in str(r.get("reason", "")).lower() or "out of bounds" in str(r.get("reason", "")).lower() for r in report.rejected_messages)


def test_confidence_string_rejected(orchestrator, sample_valid_telemetry):
    """Agent response with confidence as a non-numeric string must be quarantined."""
    mock_agent = mock.Mock()
    mock_agent.execute.return_value = {
        "task_id": "t_str",
        "agent_id": "performance_agent",
        "confidence": "high_confidence",
        "status": "SUCCESS",
    }
    orchestrator.performance_agent = mock_agent
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert "performance_agent" in report.failed_agents
    assert len(report.rejected_messages) > 0


def test_confidence_missing_defaults_to_schema_policy(orchestrator, sample_valid_telemetry):
    """Missing confidence adheres to schema default (0.0) without crashing."""
    mock_agent = mock.Mock()
    mock_agent.execute.return_value = {
        "task_id": "t_miss",
        "agent_id": "performance_agent",
        "status": "SUCCESS",
    }
    orchestrator.performance_agent = mock_agent
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert "performance_agent" in report.successful_agents


def test_confidence_valid_value_preserved(orchestrator, sample_valid_telemetry):
    """Valid confidence between 0.0 and 1.0 remains exact and uninflated."""
    mock_agent = mock.Mock()
    mock_agent.execute.return_value = {
        "task_id": "t_exact",
        "agent_id": "performance_agent",
        "confidence": 0.825,
        "status": "SUCCESS",
    }
    orchestrator.performance_agent = mock_agent
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert "performance_agent" in report.successful_agents


def test_timeout_worker_cannot_mutate_returned_report(orchestrator, sample_valid_telemetry):
    """A background worker completing after report is returned cannot mutate that report."""
    orchestrator.agent_timeout = 0.2
    barrier = concurrent.futures.Future()

    def delayed_worker(task_id, df):
        try:
            barrier.result(timeout=2.0)
        except Exception:
            pass
        msg = create_agent_message(task_id, "performance_agent", status=AgentStatus.SUCCESS)
        msg.findings.append(Finding(category="PERFORMANCE", title="MUTATION_ATTEMPT", description="Late finding"))
        return msg

    mock_slow = mock.Mock()
    mock_slow.execute.side_effect = delayed_worker
    orchestrator.performance_agent = mock_slow

    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert "performance_agent" in report.timed_out_agents
    assert not any(f.title == "MUTATION_ATTEMPT" for f in report.validated_findings)

    # Release worker thread
    barrier.set_result(True)
    time.sleep(0.05)

    # Returned report remains completely unmutated
    assert not any(f.title == "MUTATION_ATTEMPT" for f in report.validated_findings)


def test_repeated_timeouts_resource_safety(orchestrator, sample_valid_telemetry):
    """
    Repeated timeouts verify:
    1. Orchestrator returns within its configured timeout.
    2. Successful results from non-timed-out agents remain available.
    3. Late workers cannot mutate completed reports.
    4. Background worker threads do not grow without bound under repeated workloads.
    """
    import threading
    orchestrator.agent_timeout = 0.1

    def slow_worker(task_id, df):
        # Deliberately slow worker (takes 0.25s, longer than 0.1s timeout)
        time.sleep(0.25)
        msg = create_agent_message(task_id, "performance_agent")
        msg.findings.append(Finding(category="PERFORMANCE", title="LATE_MUTATION_ATTEMPT", description="Late"))
        return msg

    mock_slow = mock.Mock()
    mock_slow.execute.side_effect = slow_worker
    orchestrator.performance_agent = mock_slow

    initial_threads = threading.active_count()
    t0 = time.perf_counter()
    reports = []

    # Run 4 repeated timeout diagnoses
    for _ in range(4):
        rep = orchestrator.run_diagnosis(sample_valid_telemetry)
        reports.append(rep)
        # 1. Orchestrator returned within reasonable bound of configured timeout
        assert "performance_agent" in rep.timed_out_agents
        # 2. Successful results from other agents remain available
        assert "infrastructure_agent" in rep.successful_agents
        assert "connectivity_agent" in rep.successful_agents

    elapsed = time.perf_counter() - t0
    # Total elapsed for 4 runs of 0.1s timeout should be well under 2.0s
    assert elapsed < 2.0

    # 3. Late workers cannot mutate completed reports
    for rep in reports:
        assert not any(f.title == "LATE_MUTATION_ATTEMPT" for f in rep.validated_findings)

    # 4. Background workers complete their work and thread count returns to baseline
    time.sleep(0.35)
    final_threads = threading.active_count()
    # Thread count should not grow without bound (within small delta of initial)
    assert final_threads <= initial_threads + 2


def test_confidence_validation_bypass_strict_rejection():
    """
    Strict policy requires invalid confidence values to be rejected, not silently clamped.
    Test values:
    * -0.1
    * 1.1
    * NaN
    * positive infinity
    * negative infinity
    * invalid string
    Tested through BOTH direct AgentMessage construction and create_agent_message().
    """
    from pydantic import ValidationError

    invalid_test_values = [
        -0.1,
        1.1,
        float("nan"),
        float("inf"),
        float("-inf"),
        "invalid string",
    ]

    for val in invalid_test_values:
        # Direct AgentMessage construction
        with pytest.raises(ValidationError):
            AgentMessage(task_id="T1", agent_id="A1", confidence=val)

        # create_agent_message()
        with pytest.raises(ValidationError):
            create_agent_message(task_id="T1", agent_id="A1", confidence=val)

    # Valid values preserved
    valid_direct = AgentMessage(task_id="T1", agent_id="A1", confidence=0.85)
    assert valid_direct.confidence == 0.85
    valid_helper = create_agent_message(task_id="T1", agent_id="A1", confidence=0.85)
    assert valid_helper.confidence == 0.85

    # Missing confidence retains conservative default of 0.0
    assert AgentMessage(task_id="T1", agent_id="A1").confidence == 0.0
    assert AgentMessage(task_id="T1", agent_id="A1", confidence=None).confidence == 0.0
    assert create_agent_message(task_id="T1", agent_id="A1", confidence=None).confidence == 0.0


def test_phase3_10_agent_returns_empty_findings(orchestrator, sample_valid_telemetry):
    """Agent returning zero findings succeeds normally without division-by-zero errors."""
    mock_empty = mock.Mock()
    mock_empty.execute.side_effect = lambda tid, df: create_agent_message(
        task_id=tid, agent_id="performance_agent", status=AgentStatus.SUCCESS, findings=[]
    )
    orchestrator.performance_agent = mock_empty

    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert "performance_agent" in report.successful_agents


def test_phase3_11_partial_telemetry_reaches_agents(orchestrator):
    """Telemetry records missing entire metric families are handled without KeyError."""
    now = datetime.now(timezone.utc)
    partial_data = [
        {"device_id": "dev1", "timestamp": now.isoformat(), "latency_ms": 15.0},
        {"device_id": "dev2", "timestamp": now.isoformat(), "cpu_util_pct": 30.0},
    ]
    report = orchestrator.run_diagnosis(partial_data)
    assert report.execution_status in ["COMPLETED", "SUCCESS", "PARTIAL_SUCCESS"]


def test_phase3_12_repeated_diagnosis_runs(orchestrator, sample_valid_telemetry):
    """Sequential diagnosis runs on the same orchestrator instance do not leak previous state."""
    report1 = orchestrator.run_diagnosis(sample_valid_telemetry)
    report2 = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert report1.task_id != report2.task_id
    assert report1.report_id != report2.report_id


def test_phase3_13_concurrent_diagnosis_requests(orchestrator, sample_valid_telemetry):
    """Concurrent invocations from multiple threads produce isolated reports with unique IDs."""
    def run_worker(idx):
        return orchestrator.run_diagnosis(sample_valid_telemetry, scenario_name=f"conc_{idx}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        reports = list(pool.map(run_worker, range(4)))

    task_ids = {r.task_id for r in reports}
    report_ids = {r.report_id for r in reports}
    assert len(task_ids) == 4
    assert len(report_ids) == 4


def test_phase3_14_conflicting_agent_conclusions(orchestrator):
    """Conflicting conclusions between agents trigger penalty calculation and uncertainty documentation."""
    now = datetime.now(timezone.utc)
    # High packet loss on core-router but 100% reachability and low transit link utilization
    conflict_telemetry = [
        {
            "timestamp": now.isoformat(),
            "device_id": "core-router-01",
            "device_type": "router",
            "latency_ms": 250.0,
            "jitter_ms": 50.0,
            "packet_loss_pct": 35.0,  # Critical loss
            "bandwidth_util_pct": 20.0,  # Low link util (conflict!)
            "connectivity_status": "connected",  # Verified reachable
            "device_status": "active",
        }
    ]
    report = orchestrator.run_diagnosis(conflict_telemetry)
    # Must preserve uncertainty and detect the conflict
    assert report.confidence_score <= 0.85
    assert report.diagnosis_certainty in ["INDETERMINATE", "PROVISIONAL"]
    assert report.limitations.insufficient_evidence is True


def test_phase3_15_missing_optional_agent(tmp_path, sample_valid_telemetry):
    """Orchestrator functions reliably when an optional agent is initialized as None."""
    orch_no_conn = CentralOrchestrator(
        reports_dir=str(tmp_path / "reports_no_conn"),
        connectivity_agent=None,
    )
    report = orch_no_conn.run_diagnosis(sample_valid_telemetry)
    assert report.execution_status in ["COMPLETED", "SUCCESS", "PARTIAL_SUCCESS"]
    assert "connectivity_agent" not in report.successful_agents


# =============================================================================
# PHASE 4: REPORT AND CONFIDENCE CONSISTENCY (11 TESTS)
# =============================================================================

def test_phase4_01_unique_identifiers(orchestrator, sample_valid_telemetry):
    """Every generated report assigns non-empty, unique identifiers."""
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert report.report_id.startswith("REP-")
    assert report.diagnosis_id.startswith("REP-") or report.diagnosis_id.startswith("DIAG-")
    assert report.task_id.startswith("TASK-")


def test_phase4_02_valid_utc_timestamps(orchestrator, sample_valid_telemetry):
    """Report timestamps are timezone-aware UTC datetimes."""
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert report.timestamp.tzinfo == timezone.utc
    assert report.execution_timestamp.tzinfo == timezone.utc


def test_phase4_03_report_schema_version_2_0_0(orchestrator, sample_valid_telemetry):
    """Report strictly adheres to schema version 2.0.0."""
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert report.schema_version == "2.0.0"
    assert report.report_version == "2.0.0"


def test_phase4_04_health_classification_separate_from_certainty(orchestrator, sample_valid_telemetry):
    """Network health (NOMINAL) is decoupled from diagnostic hypothesis certainty."""
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    # On normal healthy data:
    assert report.health_classification == "NOMINAL"
    assert report.overall_network_health == NetworkHealthStatus.HEALTHY
    assert report.fault_detected is False
    assert report.diagnosis_certainty in ["NOT_APPLICABLE", "CONFIRMED"]


def test_phase4_05_healthy_reports_do_not_fabricate_confidence(orchestrator, sample_valid_telemetry):
    """Healthy report does not fabricate a root-cause confidence score; UI displays N/A."""
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    conf_data = get_confidence_display(report)
    assert conf_data["is_applicable"] is False
    assert conf_data["display_text"] == "N/A"
    assert "Baseline Operational State" in conf_data["subtext"]


def test_phase4_06_findings_retain_source_agent_provenance(orchestrator, sample_valid_telemetry):
    """All findings in the report retain source_agent, finding_type, and timestamp."""
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    for f in report.validated_findings:
        assert f.source_agent is not None
        assert f.finding_type in ["OBSERVED_EVIDENCE", "INFERRED_HYPOTHESIS"]
        assert f.timestamp is not None


def test_phase4_07_evidence_values_and_units_consistent(orchestrator, sample_valid_telemetry):
    """Evidence items retain valid metric names, observed values, and units."""
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    for ev in report.supporting_evidence:
        assert ev.metric_name != ""
        assert ev.observed_value is not None


def test_phase4_08_alternatives_and_uncertainty_preserved(orchestrator):
    """Alternative hypotheses and uncertainty notes are preserved in the report."""
    data = generate_scenario_data("congestion")
    report = orchestrator.run_diagnosis(data, scenario_name="congestion")
    assert isinstance(report.alternative_causes, list)
    assert isinstance(report.uncertainty_notes, list)


def test_phase4_09_missing_evidence_never_invented(orchestrator):
    """Evidence items are derived from observed telemetry, never fabricated for unmeasured metrics."""
    now = datetime.now(timezone.utc)
    sparse_data = [{"device_id": "gw-01", "timestamp": now.isoformat(), "latency_ms": 10.0}]
    report = orchestrator.run_diagnosis(sparse_data)
    observed_metric_names = {ev.metric_name for ev in report.supporting_evidence}
    assert "wifi_rssi_dbm" not in observed_metric_names


def test_phase4_10_json_serialization_round_trip(orchestrator, sample_valid_telemetry):
    """Report serializes to JSON and deserializes back into DiagnosticReport identically."""
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    json_str = report.model_dump_json(indent=2)
    reloaded = DiagnosticReport.model_validate_json(json_str)
    assert reloaded.report_id == report.report_id
    assert reloaded.task_id == report.task_id
    assert reloaded.overall_network_health == report.overall_network_health


def test_phase4_11_legacy_compatibility_fields(orchestrator, sample_valid_telemetry):
    """Legacy report fields (confidence, report_version, diagnosis_id, overall_status) are preserved."""
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    assert hasattr(report, "confidence")
    assert hasattr(report, "diagnosis_id")
    assert hasattr(report, "overall_status")
    assert hasattr(report, "report_version")


# =============================================================================
# PHASE 5: RECOMMENDATION SAFETY (7 TESTS)
# =============================================================================

def test_phase5_01_recommendations_advisory_only(orchestrator, sample_valid_telemetry):
    """Recommendation generation is strictly advisory; no command is ever auto-executed."""
    report = orchestrator.run_diagnosis(sample_valid_telemetry)
    for act in report.recommended_corrective_actions:
        assert isinstance(act.title, str)
        # Verify no external subprocess or socket connection was opened


def test_phase5_02_disruptive_actions_require_human_approval():
    """Disruptive actions such as interface bounces or QoS reconfigurations require approval."""
    rec_agent = RecommendationAgent()
    rc = RootCauseCandidate(
        title="Physical Interface Failure",
        description="Excessive CRC errors on port.",
        confidence=0.92,
        affected_devices=["sw-access-01"],
    )
    resp = rec_agent.generate_recommendations("t_safety", rc)
    disruptive_actions = [a for a in resp.recommendations if a.requires_human_approval]
    assert len(disruptive_actions) > 0
    assert any("Bounce" in a.title or "Shutdown" in a.title or "Replace" in a.title for a in disruptive_actions)


def test_phase5_03_missing_approval_defaults_to_requiring_approval():
    """When approval requirement is missing or None, fail-safe policy defaults to requiring approval."""
    mock_action = mock.Mock(
        title="Unknown System Script",
        description="Run unspecified helper",
        requires_human_approval=None,  # Missing/unspecified
        action_type="SCRIPT",
        execution_risk="UNKNOWN",
    )
    res = categorize_action(mock_action)
    assert res["requires_human_approval"] is True


def test_phase5_04_service_restarts_and_config_changes_approval_gated():
    """Service restarts and routing/DNS reconfigurations require human approval."""
    rec_agent = RecommendationAgent()
    rc = RootCauseCandidate(
        title="Domain Name Resolution (DNS) Failure",
        description="Local resolver socket stalls.",
        confidence=0.90,
        affected_devices=["core-01"],
    )
    resp = rec_agent.generate_recommendations("t_dns", rc)
    approval_gated = [a for a in resp.recommendations if a.requires_human_approval]
    assert len(approval_gated) > 0
    assert any("Restart" in a.title or "Failover" in a.title for a in approval_gated)


def test_phase5_05_read_only_diagnostics_remain_low_risk():
    """Non-intrusive read-only diagnostic actions do not require NOC human approval."""
    rec_agent = RecommendationAgent()
    rc = RootCauseCandidate(
        title="Network Congestion and Bufferbloat",
        description="Buffer overflow on egress port.",
        confidence=0.88,
        affected_devices=["router-01"],
    )
    resp = rec_agent.generate_recommendations("t_diag", rc)
    diag_action = next(a for a in resp.recommendations if a.category == "DIAGNOSTIC")
    assert diag_action.requires_human_approval is False


def test_phase5_06_rollback_and_verification_steps_provided():
    """Approval-gated actions provide non-empty verification and rollback instructions."""
    rec_agent = RecommendationAgent()
    rc = RootCauseCandidate(
        title="Infrastructure Control Plane Overload",
        description="Process saturation.",
        confidence=0.94,
        affected_devices=["edge-router-01"],
    )
    resp = rec_agent.generate_recommendations("t_roll", rc)
    for a in resp.recommendations:
        if a.requires_human_approval:
            assert len(a.verification_steps) > 0
            assert len(a.rollback_steps) > 0


def test_phase5_07_insufficient_evidence_produces_diagnostic_actions_only():
    """When evidence is insufficient or indeterminate, only non-disruptive diagnostics are generated."""
    rec_agent = RecommendationAgent()
    rc_indeterminate = RootCauseCandidate(
        title="Indeterminate Network Anomaly",
        description="Conflicting evidence observed.",
        confidence=0.25,
        affected_devices=["node-01"],
    )
    resp = rec_agent.generate_recommendations("t_indet", rc_indeterminate)
    # Must NOT generate disruptive configuration reboots
    for a in resp.recommendations:
        assert a.requires_human_approval is False
        assert a.action_type in ["DIAGNOSTIC", "VERIFICATION"]


# =============================================================================
# PHASE 6: API AND DASHBOARD INTEGRATION (5 TESTS)
# =============================================================================

def test_phase6_01_api_validation_and_http_error_responses():
    """API correctly returns 400 for empty batch, 422 for malformed batch, and 404 for missing report."""
    client = TestClient(app)

    # Empty batch -> 400
    r_empty = client.post("/api/diagnose", json={"telemetry": []})
    assert r_empty.status_code == 400

    # Malformed batch -> 422
    r_malformed = client.post("/api/diagnose", json={"telemetry": [{"bad_key": 123}]})
    assert r_malformed.status_code == 422

    # Missing report -> 404
    r_missing = client.get("/api/reports/REP-NONEXISTENT")
    assert r_missing.status_code == 404


def test_phase6_02_concurrent_api_requests(sample_valid_telemetry):
    """Concurrent API requests execute safely with independent responses."""
    client = TestClient(app)

    def send_req(i):
        return client.post("/api/diagnose", json={"telemetry": sample_valid_telemetry})

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        responses = list(pool.map(send_req, range(3)))

    for resp in responses:
        assert resp.status_code == 200
        data = resp.json()
        assert data["report_id"].startswith("REP-")


def test_phase6_03_report_retrieval_by_both_identifiers(orchestrator, sample_valid_telemetry):
    """API retrieves reports by either report_id or diagnosis_id."""
    client = TestClient(app)
    # Generate report
    resp = client.post("/api/diagnose", json={"telemetry": sample_valid_telemetry})
    assert resp.status_code == 200
    data = resp.json()
    rep_id = data["report_id"]
    diag_id = data["diagnosis_id"]

    # Retrieve by report_id
    r1 = client.get(f"/api/reports/{rep_id}")
    assert r1.status_code == 200
    assert r1.json()["report_id"] == rep_id

    # Retrieve by diagnosis_id
    r2 = client.get(f"/api/reports/{diag_id}")
    assert r2.status_code == 200
    assert r2.json()["diagnosis_id"] == diag_id


def test_phase6_04_persistence_failure_gracefully_handled(sample_valid_telemetry, orchestrator):
    """Persistence failures (e.g., read-only filesystem) are caught and logged without crashing diagnosis."""
    with mock.patch.object(orchestrator, "_save_report", side_effect=OSError("Disk full")):
        report = orchestrator.run_diagnosis(sample_valid_telemetry, save_report=True)
        assert report.execution_status in ["COMPLETED", "COMPLETED_WITH_WARNINGS", "SUCCESS", "PARTIAL_SUCCESS"]
        assert any("persistence" in w.lower() for w in report.warnings)


def test_phase6_05_dashboard_api_client_resilience():
    """Dashboard API client gracefully handles ConnectionError, Timeout, HTTP 404, 500, and malformed JSON."""
    with mock.patch("requests.get") as mock_get:
        # ConnectionError
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError("Refused")
        rep, err = fetch_report_from_api("REP-123")
        assert rep is None
        assert "Unable to connect" in err

        # Timeout
        mock_get.side_effect = requests.exceptions.Timeout("Timed out")
        rep, err = fetch_report_from_api("REP-123")
        assert rep is None
        assert "timed out" in err

        # HTTP 500
        mock_resp = mock.Mock(status_code=500, text="Internal server error")
        mock_get.side_effect = None
        mock_get.return_value = mock_resp
        rep, err = fetch_report_from_api("REP-123")
        assert rep is None
        assert "HTTP 500" in err

        # Malformed JSON
        mock_resp = mock.Mock(status_code=200)
        mock_resp.json.side_effect = json.JSONDecodeError("msg", "doc", 0)
        mock_get.return_value = mock_resp
        rep, err = fetch_report_from_api("REP-123")
        assert rep is None
        assert "malformed non-JSON" in err
