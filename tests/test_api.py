from fastapi.testclient import TestClient
import pytest

from api.main import app

client = TestClient(app)


def test_api_health():
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert len(data["active_agents"]) == 5


def test_api_get_scenarios():
    res = client.get("/api/scenarios")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 8
    sc_ids = [s["scenario_id"] for s in data["scenarios"]]
    assert "normal" in sc_ids
    assert "congestion" in sc_ids


def test_api_get_scenario_detail():
    res = client.get("/api/scenarios/congestion")
    assert res.status_code == 200
    data = res.json()
    assert data["scenario_id"] == "congestion"
    assert len(data["records"]) > 0


def test_api_diagnose_scenario():
    res = client.post("/api/diagnose", json={"scenario_id": "normal"})
    assert res.status_code == 200
    report = res.json()
    assert report["overall_network_health"] == "HEALTHY"
    assert "probable_root_cause" in report
    assert report["confidence_score"] >= 0.85
    report_id = report["report_id"]

    # Verify report retrieval
    res_get = client.get(f"/api/reports/{report_id}")
    assert res_get.status_code == 200
    assert res_get.json()["report_id"] == report_id


def test_api_diagnose_custom_telemetry():
    telemetry = [
        {"device_id": "r1", "latency_ms": 15.0, "bandwidth_util_pct": 30.0},
        {"device_id": "r1", "latency_ms": 14.0, "bandwidth_util_pct": 35.0},
    ]
    res = client.post("/api/diagnose", json={"telemetry": telemetry})
    assert res.status_code == 200
    report = res.json()
    assert report["task_id"].startswith("TASK-")


def test_api_upload_csv():
    csv_content = (
        "device_id,latency_ms,packet_loss_pct\n"
        "router-01,15.2,0.0\n"
        "switch-01,12.0,0.0\n"
    )
    res = client.post(
        "/api/telemetry/upload-csv",
        files={"file": ("test.csv", csv_content, "text/csv")},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["record_count"] == 2
    assert "device_id" in data["columns"]


def test_api_list_reports():
    res = client.get("/api/reports")
    assert res.status_code == 200
    data = res.json()
    assert "reports" in data
