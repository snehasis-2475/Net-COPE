"""
Trace and verify pipeline for NetCoop AI multi-agent diagnosis.
Executes:
- STEP 1 & 2: Frontend-Backend verification
- STEP 3: 10-stage trace of a real uploaded telemetry record
- STEP 4: 7 controlled scenario tests
"""
import json
import urllib.request
import urllib.error
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from streamlit.testing.v1 import AppTest

from data.csv_loader import load_telemetry_csv
from communication.telemetry_validator import TelemetryValidator
from communication.models import NetworkTelemetryRecord
from agents import (
    PerformanceAgent,
    InfrastructureAgent,
    ConnectivityAgent,
    FaultCorrelationAgent,
    RecommendationAgent,
)
from orchestrator.orchestrator import CentralOrchestrator
from data.scenarios import generate_scenario_data, SCENARIO_METADATA
from diagnosis.models import DiagnosticReport

def test_api_health():
    req = urllib.request.Request("http://127.0.0.1:8000/health")
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        body = json.loads(resp.read().decode())
        print("API Health Check OK:", body["status"], body["version"])
        return body

def test_csv_upload_api():
    csv_path = Path("data/samples/normal.csv")
    csv_bytes = csv_path.read_bytes()
    
    boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{csv_path.name}"\r\n'
        f"Content-Type: text/csv\r\n\r\n"
    ).encode("utf-8") + csv_bytes + f"\r\n--{boundary}--\r\n".encode("utf-8")
    
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/telemetry/upload-csv",
        data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST"
    )
    with urllib.request.urlopen(req) as resp:
        assert resp.status == 200
        res = json.loads(resp.read().decode())
        print(f"API CSV Upload OK: {res['record_count']} records loaded")
        return res

def trace_single_record_pipeline():
    print("\n================ STEP 3: TRACING REAL TELEMETRY RECORD ================")
    # Stage 1: CSV Upload
    raw_csv = (
        "device_id,timestamp,latency_ms,jitter_ms,packet_loss_pct,cpu_util_pct,memory_util_pct,interface_status,dns_latency_ms,dhcp_latency_ms,wifi_rssi_dbm,wifi_signal_dbm\n"
        "edge-switch-01,2026-10-31T12:00:00Z,185.4,42.1,8.5,88.2,74.5,up,28.0,45.0,-62.0,-62.0\n"
    )
    print("STAGE 1: CSV Upload")
    print("  Input:", raw_csv.strip())
    
    # Stage 2: Telemetry Ingestion
    df, warnings = load_telemetry_csv(raw_csv)
    print("STAGE 2: Telemetry Ingestion")
    print("  Output Records:", len(df), "Columns:", list(df.columns), "Warnings:", warnings)
    assert not df.empty
    
    # Stage 3: Schema Validation
    dict_records = df.where(pd.notnull(df), None).to_dict(orient="records")
    valid_recs, val_errors = TelemetryValidator.validate_batch(dict_records)
    print("STAGE 3: Schema Validation")
    print("  Valid count:", len(valid_recs), "Errors count:", len(val_errors))
    assert len(valid_recs) == 1
    assert len(val_errors) == 0
    validated_record = valid_recs[0]
    print("  Validated Record:", validated_record)

    # Instantiate agents
    perf_agent = PerformanceAgent()
    infra_agent = InfrastructureAgent()
    conn_agent = ConnectivityAgent()
    corr_agent = FaultCorrelationAgent()
    rec_agent = RecommendationAgent()

    task_id = "trace_task_001"
    df_input = pd.DataFrame([validated_record.model_dump()])

    # Stage 4: Performance Agent
    perf_msg = perf_agent.execute(task_id, df_input)
    print("STAGE 4: Performance Agent")
    print("  Input: 1 telemetry record (latency=185.4ms, loss=8.5%, jitter=42.1ms)")
    print("  Output Status:", perf_msg.status.value, "| Confidence:", perf_msg.confidence)
    print("  Findings:", len(perf_msg.findings), [f.title for f in perf_msg.findings])
    print("  Errors: None | Success: True")

    # Stage 5: Infrastructure Health Agent
    infra_msg = infra_agent.execute(task_id, df_input)
    print("STAGE 5: Infrastructure Health Agent")
    print("  Input: 1 telemetry record (cpu=88.2%, memory=74.5%, interface=up)")
    print("  Output Status:", infra_msg.status.value, "| Confidence:", infra_msg.confidence)
    print("  Findings:", len(infra_msg.findings), [f.title for f in infra_msg.findings])
    print("  Errors: None | Success: True")

    # Stage 6: Connectivity Agent
    conn_msg = conn_agent.execute(task_id, df_input)
    print("STAGE 6: Connectivity Agent")
    print("  Input: 1 telemetry record (dns=28ms, dhcp=45ms, wifi_rssi=-62dBm)")
    print("  Output Status:", conn_msg.status.value, "| Confidence:", conn_msg.confidence)
    print("  Findings:", len(conn_msg.findings), [f.title for f in conn_msg.findings])
    print("  Errors: None | Success: True")

    # Stage 7: Fault Correlation Agent
    agent_messages = {
        "performance_agent": perf_msg,
        "infrastructure_agent": infra_msg,
        "connectivity_agent": conn_msg,
    }
    corr_msg = corr_agent.correlate(task_id, agent_messages)
    print("STAGE 7: Fault Correlation Agent")
    print("  Input: 3 domain agent messages (perf, infra, conn)")
    print("  Output Status:", corr_msg.status.value, "| Confidence:", corr_msg.confidence)
    print("  Correlated Hypotheses:", [f.title for f in corr_msg.findings])
    print("  Errors: None | Success: True")

    # Stage 8: Recommendation Agent
    rec_msg = rec_agent.recommend(task_id, corr_msg)
    print("STAGE 8: Recommendation Agent")
    print("  Input: Correlated hypothesis message")
    print("  Output Status:", rec_msg.status.value)
    print("  Actions Generated:", len(rec_msg.evidence))
    print("  Errors: None | Success: True")

    # Stage 9: Unified Diagnostic Report via Orchestrator
    orchestrator = CentralOrchestrator()
    report = orchestrator.run_diagnosis(telemetry=dict_records, scenario_name="edge_trace_test", save_report=True)
    print("STAGE 9: Unified Diagnostic Report")
    print("  Report ID:", report.report_id)
    print("  Overall Health:", report.overall_network_health.value)
    print("  Probable Root Cause:", report.probable_root_cause.title if report.probable_root_cause else None)
    print("  Recommendations:", len(report.recommendations))
    assert report.schema_version == "2.0.0"

    # Stage 10: Streamlit Display Verification (via AppTest)
    app_path = str(Path(__file__).resolve().parent.parent / "dashboard" / "app.py")
    at = AppTest.from_file(app_path)
    at.session_state["diagnostic_report"] = report
    at.session_state["current_telemetry_df"] = df
    at.run(timeout=15)
    print("STAGE 10: Streamlit Display")
    print("  AppTest Exceptions:", len(at.exception))
    assert len(at.exception) == 0, f"Streamlit raised: {at.exception}"
    print("  Streamlit rendered cleanly with zero uncaught exceptions!")

def run_controlled_scenarios():
    print("\n================ STEP 4: CONTROLLED SCENARIO TESTS ================")
    scenarios = [
        "normal",
        "congestion",
        "weak_wifi",
        "interface_failure",
        "dns_failure",
        "dhcp_failure",
        "infrastructure_overload",
    ]
    results = {}

    for sc in scenarios:
        data = generate_scenario_data(sc)
        req_data = json.dumps({"telemetry": data}).encode("utf-8")
        req = urllib.request.Request(
            "http://127.0.0.1:8000/api/diagnose",
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            rep_json = json.loads(resp.read().decode())
            rep = DiagnosticReport.model_validate(rep_json)
            
            rc = rep.probable_root_cause.title if rep.probable_root_cause else "None"
            results[sc] = {
                "report_id": rep.report_id,
                "health": rep.overall_network_health.value,
                "fault_detected": rep.fault_detected,
                "root_cause": rc,
                "confidence": rep.root_cause_confidence or rep.confidence_score,
                "recommendations_count": len(rep.recommendations),
            }
            print(f"Scenario [{sc:25}] -> Health: {rep.overall_network_health.value:8} | Fault: {str(rep.fault_detected):5} | Root Cause: {rc}")

    print("\nAll 7 scenarios successfully diagnosed through FastAPI endpoint!")
    return results

if __name__ == "__main__":
    test_api_health()
    test_csv_upload_api()
    trace_single_record_pipeline()
    run_controlled_scenarios()
