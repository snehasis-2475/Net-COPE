with open("tests/test_csv_loader.py", "r", encoding="utf-8") as f:
    content = f.read()

new_test = '''

def test_load_organizer_mock_telemetry_csv_and_diagnose():
    """Verify that the official hackathon organizer mock dataset loads, parses, and diagnoses cleanly."""
    from pathlib import Path
    from orchestrator.orchestrator import CentralOrchestrator
    from diagnosis.models import NetworkHealthStatus

    csv_file = Path("data/samples/organizer_mock_telemetry.csv")
    assert csv_file.exists(), "Organizer mock telemetry CSV must exist in data/samples/"

    df, warnings = load_telemetry_csv(csv_file)
    assert not df.empty
    assert len(df) == 100
    assert "cpu_util_pct" in df.columns
    assert "bandwidth_util_pct" in df.columns
    assert "device_id" in df.columns

    orch = CentralOrchestrator()
    report = orch.run_diagnosis(df, scenario_name="Organizer Benchmark")
    assert report.fault_detected is True
    assert report.overall_network_health in (NetworkHealthStatus.CRITICAL, NetworkHealthStatus.DEGRADED)
    assert "congestion" in report.probable_root_cause.title.lower() or "bufferbloat" in report.probable_root_cause.title.lower()
    assert len(report.affected_devices) > 0
    assert len(report.recommended_corrective_actions) >= 3
    assert len(report.errors) == 0
'''

if "test_load_organizer_mock_telemetry_csv_and_diagnose" not in content:
    content += new_test
    with open("tests/test_csv_loader.py", "w", encoding="utf-8") as f:
        f.write(content)

print("test_csv_loader.py updated with organizer mock test!")

