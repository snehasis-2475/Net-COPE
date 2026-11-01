with open("data/scenarios.py", "r", encoding="utf-8") as f:
    content = f.read()

helper = '''
def _load_organizer_mock() -> List[Dict[str, Any]]:
    """Loads the official organizer benchmark mock dataset from disk."""
    csv_path = SAMPLE_DIR / "organizer_mock_telemetry.csv"
    if not csv_path.exists():
        csv_path = Path(__file__).resolve().parent / "samples" / "organizer_mock_telemetry.csv"
    if csv_path.exists():
        from data.csv_loader import load_telemetry_csv
        df, _ = load_telemetry_csv(csv_path)
        return df.to_dict(orient="records")
    return []
'''

if "def _load_organizer_mock" not in content:
    # insert helper before generate_scenario_data
    content = content.replace("def generate_scenario_data", helper + "\ndef generate_scenario_data")

# update dispatch
target_dispatch = '''    elif scenario_id == "invalid_telemetry":
        return _generate_invalid(now)'''

new_dispatch = '''    elif scenario_id == "invalid_telemetry":
        return _generate_invalid(now)
    elif scenario_id in ("organizer_mock", "organizer_benchmark"):
        return _load_organizer_mock()'''

if target_dispatch in content:
    content = content.replace(target_dispatch, new_dispatch)

# update metadata
target_meta = '''    "invalid_telemetry": {
        "title": "8. Invalid Telemetry Dataset",
        "description": "Corrupt telemetry with missing IDs, negative latencies, and out-of-range values testing validation resilience.",
        "expected_root_cause": "Invalid or Empty Telemetry",
    },'''

new_meta = '''    "invalid_telemetry": {
        "title": "8. Invalid Telemetry Dataset",
        "description": "Corrupt telemetry with missing IDs, negative latencies, and out-of-range values testing validation resilience.",
        "expected_root_cause": "Invalid or Empty Telemetry",
    },
    "organizer_mock": {
        "title": "9. Official Organizer Benchmark (Campus Switches)",
        "description": "Official 100-record hackathon test dataset with 10 campus switches (SW_CAMPUS_1 to SW_CAMPUS_10) experiencing progressive bufferbloat, queue drops, and interface saturation.",
        "expected_root_cause": "Network Bandwidth Congestion & Bufferbloat",
    },'''

if target_meta in content:
    content = content.replace(target_meta, new_meta)

with open("data/scenarios.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Scenarios updated successfully!")

