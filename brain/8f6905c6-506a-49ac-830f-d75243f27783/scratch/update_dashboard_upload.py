with open("dashboard/app.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update radio options
old_radio = '''input_mode = st.sidebar.radio(
    "Telemetry Input Source",
    options=["Synthetic Scenarios", "CSV File Upload", "Saved Report Lookup"],
    index=0,
)'''

new_radio = '''input_mode = st.sidebar.radio(
    "Telemetry Input Source",
    options=["Synthetic Scenarios", "CSV / JSON File Upload", "Saved Report Lookup"],
    index=0,
)'''

if old_radio in content:
    content = content.replace(old_radio, new_radio, 1)

# 2. Update upload block in sidebar
old_upload = '''elif input_mode == "CSV File Upload":
    uploaded_file = st.sidebar.file_uploader("Upload Telemetry CSV", type=["csv"])
    if uploaded_file is not None:
        df, warnings = load_telemetry_csv(uploaded_file.getvalue())
        if not df.empty:
            st.session_state.current_telemetry_df = df
            st.session_state.scenario_name = uploaded_file.name
            st.session_state.diagnostic_report = None
            st.sidebar.success(f"Parsed {len(df)} records from CSV.")
            if warnings:
                for w in warnings:
                    st.sidebar.warning(w)
        else:
            st.sidebar.error("Failed to load telemetry from CSV.")'''

new_upload = '''elif input_mode in ("CSV File Upload", "CSV / JSON File Upload"):
    st.sidebar.markdown("### Upload Telemetry File")
    uploaded_file = st.sidebar.file_uploader(
        "Upload Telemetry (CSV or JSON)",
        type=["csv", "json"],
        help="Upload operational network telemetry in RFC-4180 CSV or JSON format.",
    )
    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        fname = uploaded_file.name.lower()
        if fname.endswith(".json"):
            import json as _json
            try:
                raw_json = _json.loads(file_bytes.decode("utf-8"))
                records_list = raw_json if isinstance(raw_json, list) else raw_json.get("records", raw_json.get("telemetry", [raw_json]))
                df = pd.DataFrame(records_list)
                st.session_state.current_telemetry_df = df
                st.session_state.scenario_name = uploaded_file.name
                st.session_state.diagnostic_report = None
                st.sidebar.success(f"Parsed {len(df)} records from JSON.")
            except Exception as json_err:
                st.sidebar.error(f"JSON parsing error: {json_err}")
        else:
            df, warnings = load_telemetry_csv(file_bytes)
            if not df.empty:
                st.session_state.current_telemetry_df = df
                st.session_state.scenario_name = uploaded_file.name
                st.session_state.diagnostic_report = None
                st.sidebar.success(f"Parsed {len(df)} records from CSV.")
                if warnings:
                    for w in warnings:
                        st.sidebar.warning(w)
            else:
                st.sidebar.error("Failed to load telemetry from CSV.")'''

if old_upload in content:
    content = content.replace(old_upload, new_upload, 1)

# 3. Add organizer benchmark to demo scenarios
old_scenarios = '''        ("infrastructure_overload", "Infrastructure Overload (CPU & Memory Saturation)"),
        ("silent_drift", "Silent Degradation (Rolling Baseline Anomaly Drift)"),
        ("normal", "Healthy Network (All Metrics Nominal Baseline)"),
    ]'''

new_scenarios = '''        ("infrastructure_overload", "Infrastructure Overload (CPU & Memory Saturation)"),
        ("silent_drift", "Silent Degradation (Rolling Baseline Anomaly Drift)"),
        ("organizer_mock", "Official Organizer Benchmark (10 Campus Switches Fabric)"),
        ("normal", "Healthy Network (All Metrics Nominal Baseline)"),
    ]'''

if old_scenarios in content:
    content = content.replace(old_scenarios, new_scenarios, 1)

# 4. Add direct file uploader in tab_demo
old_demo_status = '''    if inject_btn:
        with st.status("Diagnosing Network Incident...", expanded=True) as status:'''

new_demo_upload = '''    with st.expander("📁 Upload Custom Telemetry Dataset (CSV or JSON)", expanded=False):
        st.markdown(
            "Upload an operational telemetry dataset exported from network monitors (CSV or JSON). "
            "NetCoop AI will automatically normalize fields and execute multi-agent causal correlation."
        )
        main_uploaded_file = st.file_uploader(
            "Drop or browse a CSV / JSON telemetry file",
            type=["csv", "json"],
            key="tab_demo_file_uploader",
        )
        if main_uploaded_file is not None:
            raw_bytes = main_uploaded_file.getvalue()
            if main_uploaded_file.name.lower().endswith(".json"):
                import json as _json
                try:
                    loaded_json = _json.loads(raw_bytes.decode("utf-8"))
                    items = loaded_json if isinstance(loaded_json, list) else loaded_json.get("records", loaded_json.get("telemetry", [loaded_json]))
                    up_df = pd.DataFrame(items)
                    st.success(f"Parsed {len(up_df)} records from JSON file: `{main_uploaded_file.name}`.")
                    if st.button("Diagnose Uploaded JSON", type="primary", key="btn_diag_demo_json"):
                        st.session_state.current_telemetry_df = up_df
                        st.session_state.scenario_name = main_uploaded_file.name
                        rep = orchestrator.run_diagnosis(up_df, scenario_name=main_uploaded_file.name, save_report=True)
                        st.session_state.diagnostic_report = rep
                        st.rerun()
                except Exception as jerr:
                    st.error(f"Failed to parse JSON: {jerr}")
            else:
                up_df, up_warns = load_telemetry_csv(raw_bytes)
                if not up_df.empty:
                    st.success(f"Parsed {len(up_df)} records from CSV file: `{main_uploaded_file.name}`.")
                    if up_warns:
                        for w in up_warns:
                            st.warning(w)
                    if st.button("Diagnose Uploaded CSV", type="primary", key="btn_diag_demo_csv"):
                        st.session_state.current_telemetry_df = up_df
                        st.session_state.scenario_name = main_uploaded_file.name
                        rep = orchestrator.run_diagnosis(up_df, scenario_name=main_uploaded_file.name, save_report=True)
                        st.session_state.diagnostic_report = rep
                        st.rerun()
                else:
                    st.error("Failed to load telemetry from CSV.")

    if inject_btn:
        with st.status("Diagnosing Network Incident...", expanded=True) as status:'''

if old_demo_status in content:
    content = content.replace(old_demo_status, new_demo_upload, 1)

with open("dashboard/app.py", "w", encoding="utf-8") as f:
    f.write(content)

print("dashboard/app.py successfully updated with CSV/JSON upload!")

