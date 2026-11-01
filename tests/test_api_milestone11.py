"""
Milestone 11: FastAPI Integration and Validation Tests.

Implements all 20 required validation, endpoint contract, robustness, and concurrency tests:
1. Valid congestion diagnosis request.
2. Valid DNS failure diagnosis request.
3. Valid healthy-network request.
4. Missing required request fields.
5. Malformed telemetry.
6. Unsupported scenario.
7. Empty telemetry batch.
8. Partially invalid telemetry batch.
9. Missing optional telemetry fields.
10. Invalid metric types and values.
11. Report lookup by report ID.
12. Report lookup by diagnosis ID.
13. Unknown report ID.
14. Orchestrator exception.
15. Agent timeout and partial agent failure.
16. Report persistence failure.
17. JSON serialization of complete schema 2.0.0 reports.
18. OpenAPI schema generation.
19. Concurrent diagnosis requests.
20. Backward compatibility with existing API behavior.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from api.main import app, orchestrator
from communication.models import AgentMessage, AgentStatus
from diagnosis.models import DiagnosticReport, NetworkHealthStatus


@pytest.fixture
def client(tmp_path):
    orchestrator.reports_dir = tmp_path / "test_api_reports"
    orchestrator.reports_dir.mkdir(parents=True, exist_ok=True)
    return TestClient(app)


# 1. Valid congestion diagnosis request
def test_1_valid_congestion_diagnosis_request(client):
    response = client.post("/api/diagnose", json={"scenario_id": "congestion"})
    assert response.status_code == 200
    data = response.json()
    assert data["schema_version"] == "2.0.0"
    assert data["fault_detected"] is True
    assert "congestion" in data["probable_root_cause"]["title"].lower() or "congestion" in data["selected_root_cause"]["title"].lower()
    assert len(data["recommendations"]) > 0


# 2. Valid DNS failure diagnosis request
def test_2_valid_dns_failure_diagnosis_request(client):
    response = client.post("/api/diagnose", json={"scenario_id": "dns_failure"})
    assert response.status_code == 200
    data = response.json()
    assert data["fault_detected"] is True
    assert "dns" in data["selected_root_cause"]["title"].lower()
    assert data["diagnosis_certainty"] in ["CONFIRMED", "PROVISIONAL"]


# 3. Valid healthy-network request
def test_3_valid_healthy_network_request(client):
    response = client.post("/api/diagnose", json={"scenario_id": "normal"})
    assert response.status_code == 200
    data = response.json()
    assert data["fault_detected"] is False
    assert data["health_classification"] == "NOMINAL"
    assert data["diagnosis_certainty"] == "NOT_APPLICABLE"
    assert data["root_cause_confidence"] is None
    assert "nominal" in data["summary"].lower() or "no active faults" in data["summary"].lower()


# 4. Missing required request fields
def test_4_missing_required_request_fields(client):
    # Empty body dict
    res_empty = client.post("/api/diagnose", json={})
    assert res_empty.status_code == 400
    assert "detail" in res_empty.json()
    assert "Missing required fields" in res_empty.json()["detail"]

    # Explicit null fields
    res_null = client.post("/api/diagnose", json={"scenario_id": None, "telemetry": None})
    assert res_null.status_code == 400
    assert "Missing required fields" in res_null.json()["detail"]


# 5. Malformed telemetry
def test_5_malformed_telemetry(client):
    # Completely invalid record missing device_id and timestamp
    bad_telemetry = [{"random_junk": "invalid", "another_field": 123}]
    response = client.post("/api/diagnose", json={"telemetry": bad_telemetry})
    assert response.status_code == 422
    data = response.json()
    assert data["error"] == "Malformed Telemetry Batch"
    assert "validation_errors" in data
    assert len(data["validation_errors"]) > 0
    # Field identification
    assert any(err["field"] == "device_id" for err in data["validation_errors"])


# 6. Unsupported scenario
def test_6_unsupported_scenario(client):
    response = client.post("/api/diagnose", json={"scenario_id": "unsupported_alien_attack"})
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "not found" in data["detail"].lower()
    assert "Available scenarios" in data["detail"]


# 7. Empty telemetry batch
def test_7_empty_telemetry_batch(client):
    response = client.post("/api/diagnose", json={"telemetry": []})
    assert response.status_code == 400
    assert "cannot be empty" in response.json()["detail"].lower()


# 8. Partially invalid telemetry batch
def test_8_partially_invalid_telemetry_batch(client):
    partially_invalid = [
        # Valid record 1
        {
            "timestamp": "2026-10-31T12:00:00Z",
            "device_id": "core-router-01",
            "latency_ms": 15.0,
            "packet_loss_pct": 0.0,
        },
        # Corrupt record 2 (missing device_id)
        {
            "timestamp": "2026-10-31T12:00:00Z",
            "latency_ms": 20.0,
        },
        # Valid record 3
        {
            "timestamp": "2026-10-31T12:00:00Z",
            "device_id": "edge-switch-01",
            "latency_ms": 18.0,
            "packet_loss_pct": 0.0,
        },
    ]
    response = client.post("/api/diagnose", json={"telemetry": partially_invalid})
    assert response.status_code == 200
    data = response.json()
    # Diagnosis succeeded on valid records
    assert data["execution_status"] in ["COMPLETED", "COMPLETED_WITH_WARNINGS"]
    # Corrupt record was documented in limitations
    assert len(data["limitations"]["invalid_records"]) > 0


# 9. Missing optional telemetry fields
def test_9_missing_optional_telemetry_fields(client):
    minimal_telemetry = [
        {
            "timestamp": "2026-10-31T12:00:00Z",
            "device_id": "core-router-01",
            "latency_ms": 12.0,
            "packet_loss_pct": 0.0,
            # cpu_utilization_pct and memory_utilization_pct omitted
        }
    ]
    response = client.post("/api/diagnose", json={"telemetry": minimal_telemetry})
    assert response.status_code == 200
    data = response.json()
    # Missing optional metrics documented in missing_telemetry
    assert "cpu_utilization_pct" in data["limitations"]["missing_telemetry"]
    assert "memory_utilization_pct" in data["limitations"]["missing_telemetry"]


# 10. Invalid metric types and values
def test_10_invalid_metric_types_and_values(client):
    # Negative latency value
    bad_value_batch = [
        {
            "timestamp": "2026-10-31T12:00:00Z",
            "device_id": "core-router-01",
            "latency_ms": -99.9,
        }
    ]
    response = client.post("/api/diagnose", json={"telemetry": bad_value_batch})
    assert response.status_code == 422
    data = response.json()
    assert any(err["field"] == "latency_ms" for err in data["validation_errors"])
    assert any("negative" in err["message"].lower() for err in data["validation_errors"])


# 11. Report lookup by report ID
def test_11_report_lookup_by_report_id(client):
    create_res = client.post("/api/diagnose", json={"scenario_id": "dns_failure"})
    assert create_res.status_code == 200
    rep_id = create_res.json()["report_id"]

    get_res = client.get(f"/api/reports/{rep_id}")
    assert get_res.status_code == 200
    assert get_res.json()["report_id"] == rep_id
    assert get_res.json()["schema_version"] == "2.0.0"


# 12. Report lookup by diagnosis ID
def test_12_report_lookup_by_diagnosis_id(client):
    create_res = client.post("/api/diagnose", json={"scenario_id": "weak_wifi"})
    assert create_res.status_code == 200
    diag_id = create_res.json()["diagnosis_id"]

    get_res = client.get(f"/api/reports/{diag_id}")
    assert get_res.status_code == 200
    assert get_res.json()["diagnosis_id"] == diag_id


# 13. Unknown report ID
def test_13_unknown_report_id(client):
    response = client.get("/api/reports/REP-NONEXISTENT-999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# 14. Orchestrator exception
def test_14_orchestrator_exception(client, monkeypatch):
    def mock_broken_diagnosis(*args, **kwargs):
        raise RuntimeError("Simulated internal database engine failure")

    monkeypatch.setattr(orchestrator, "run_diagnosis", mock_broken_diagnosis)
    response = client.post("/api/diagnose", json={"scenario_id": "normal"})
    assert response.status_code == 500
    data = response.json()
    # Verify no stack trace or internal details leaked
    assert "Traceback" not in str(data)
    assert "Simulated internal database engine failure" not in str(data)
    assert "internal error" in data["detail"].lower()


# 15. Agent timeout and partial agent failure
def test_15_agent_timeout_and_partial_failure(client, monkeypatch):
    class TimeoutAgent:
        def execute(self, task_id, df):
            import time
            time.sleep(0.3)
            return AgentMessage(task_id=task_id, agent_id="performance_agent")

    old_timeout = orchestrator.agent_timeout
    old_agent = orchestrator.performance_agent
    try:
        orchestrator.agent_timeout = 0.05
        orchestrator.performance_agent = TimeoutAgent()
        response = client.post("/api/diagnose", json={"scenario_id": "normal"})
        assert response.status_code == 200
        data = response.json()
        assert data["overall_status"] == "COMPLETED_WITH_WARNINGS"
        assert "performance_agent" in data["limitations"]["failed_or_timed_out_agents"]
    finally:
        orchestrator.agent_timeout = old_timeout
        orchestrator.performance_agent = old_agent


# 16. Report persistence failure
def test_16_report_persistence_failure(client, monkeypatch):
    def mock_save_fail(report):
        raise OSError("Read-only file system (mocked)")

    monkeypatch.setattr(orchestrator, "_save_report", mock_save_fail)
    response = client.post("/api/diagnose", json={"scenario_id": "congestion"})
    # Diagnosis still succeeds even if disk persistence throws OSError
    assert response.status_code == 200
    data = response.json()
    assert any("persistence warning" in w.lower() for w in data["warnings"])


# 17. JSON serialization of complete schema 2.0.0 reports
def test_17_json_serialization_of_complete_schema_2_report(client):
    response = client.post("/api/diagnose", json={"scenario_id": "interface_failure"})
    assert response.status_code == 200
    data = response.json()

    # Essential Schema 2.0.0 sections
    expected_fields = [
        "report_id", "diagnosis_id", "task_id", "timestamp", "execution_timestamp",
        "schema_version", "report_version", "execution_duration_ms", "overall_status",
        "execution_status", "overall_network_health", "health_classification",
        "fault_detected", "diagnosis_certainty", "confidence_interpretation",
        "summary", "agent_execution_summary", "successful_agents", "validated_findings",
        "selected_root_cause", "recommendations", "limitations", "warnings",
    ]
    for field in expected_fields:
        assert field in data, f"Missing field in serialized JSON: {field}"
    assert data["schema_version"] == "2.0.0"


# 18. OpenAPI schema generation
def test_18_openapi_schema_generation(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["version"] == "2.0.0"
    paths = schema["paths"]
    assert "/api/diagnose" in paths
    assert "/api/reports" in paths
    assert "/api/reports/{report_id}" in paths
    assert "/health" in paths
    assert "/api/scenarios" in paths
    # Verify documentation components exist
    assert "DiagnosticReport" in schema["components"]["schemas"]
    assert "DiagnosisRequest" in schema["components"]["schemas"]
    assert "ErrorResponse" in schema["components"]["schemas"]


# 19. Concurrent diagnosis requests
def test_19_concurrent_diagnosis_requests(client):
    scenarios = ["normal", "congestion", "dns_failure", "weak_wifi", "dhcp_failure"]

    def call_diagnose(sc_name):
        return client.post("/api/diagnose", json={"scenario_id": sc_name})

    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(call_diagnose, scenarios))

    report_ids = set()
    diagnosis_ids = set()
    for res in results:
        assert res.status_code == 200
        data = res.json()
        report_ids.add(data["report_id"])
        diagnosis_ids.add(data["diagnosis_id"])

    # Ensure zero ID collisions across concurrent calls
    assert len(report_ids) == len(scenarios)
    assert len(diagnosis_ids) == len(scenarios)


# 20. Backward compatibility with existing API behavior
def test_20_backward_compatibility_with_existing_api_behavior(client):
    # Old clients expecting probable_root_cause, confidence_score, and recommended_corrective_actions
    response = client.post("/api/diagnose", json={"scenario_id": "congestion"})
    assert response.status_code == 200
    data = response.json()

    assert "probable_root_cause" in data
    assert "confidence_score" in data
    assert "recommended_corrective_actions" in data
    assert data["probable_root_cause"]["title"] == data["selected_root_cause"]["title"]
    assert data["confidence_score"] == data["confidence"]
    assert len(data["recommended_corrective_actions"]) == len(data["recommendations"])

    # GET /api/reports list backward compatibility
    list_res = client.get("/api/reports")
    assert list_res.status_code == 200
    reports = list_res.json()["reports"]
    for r in reports:
        assert "report_id" in r
        assert "confidence_score" in r
        assert "probable_root_cause" in r


# 21. Upload CSV with missing optional fields and run diagnosis
def test_21_csv_upload_and_diagnosis_with_missing_optional_metrics(client):
    csv_bytes = (
        b"device_id,latency_ms,jitter_ms,packet_loss_pct,cpu_util_pct\n"
        b"router-01,15.2,1.8,0.0,35.0\n"
        b"switch-01,5.1,0.4,0.0,22.0\n"
    )
    # 1. Upload CSV
    upload_res = client.post(
        "/api/telemetry/upload-csv",
        files={"file": ("test_missing_opt.csv", csv_bytes, "text/csv")},
    )
    assert upload_res.status_code == 200
    upload_data = upload_res.json()
    assert upload_data["record_count"] == 2
    assert len(upload_data["sample_records"]) == 2

    # 2. Run diagnosis on records parsed from CSV
    diag_res = client.post(
        "/api/diagnose",
        json={"telemetry": upload_data["sample_records"]},
    )
    assert diag_res.status_code == 200
    diag_data = diag_res.json()
    assert diag_data["schema_version"] == "2.0.0"
    assert "report_id" in diag_data

