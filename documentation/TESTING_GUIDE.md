# NetCoop AI — Testing Guide & Verification Suite

## 1. Overview

The NetCoop AI testing framework utilizes **Pytest** to ensure deterministic validation across all specialized agents, schemas, orchestrator pipelines, scenarios, and REST endpoints.

---

## 2. Running Automated Tests

Run the full test suite with verbose output:
```powershell
.venv\Scripts\pytest -v
```

Run tests with test summary and timings:
```powershell
.venv\Scripts\pytest -v --durations=10
```

Run individual test modules:
```powershell
# Test message schemas and serialization
.venv\Scripts\pytest tests/test_models.py -v

# Test individual agents
.venv\Scripts\pytest tests/test_performance_agent.py -v
.venv\Scripts\pytest tests/test_infrastructure_agent.py -v
.venv\Scripts\pytest tests/test_connectivity_agent.py -v
.venv\Scripts\pytest tests/test_correlation_agent.py -v
.venv\Scripts\pytest tests/test_recommendation_agent.py -v

# Test central orchestrator and failure tolerance
.venv\Scripts\pytest tests/test_orchestrator.py -v

# Test all 8 built-in scenarios end-to-end
.venv\Scripts\pytest tests/test_scenarios.py -v

# Test FastAPI endpoints
.venv\Scripts\pytest tests/test_api.py -v
```

---

## 3. Test Coverage Matrix

| Test Module | Coverage Scope |
| :--- | :--- |
| `test_models.py` | Pydantic v2 serialization, deserialization, confidence clamping [0.0, 1.0], schema validation errors. |
| `test_performance_agent.py` | Nominal performance, high latency, jitter spikes, packet loss, bandwidth saturation, empty datasets. |
| `test_infrastructure_agent.py`| CPU/RAM overload, interface errors, queue drops, down/flapping interface states. |
| `test_connectivity_agent.py` | DNS timeout/servfail, DHCP exhaustion/timeouts, weak Wi-Fi RF attenuation (-85 dBm), low SNR. |
| `test_correlation_agent.py` | Nominal correlation, multi-symptom causal inference, conflict resolution, insufficient evidence handling. |
| `test_recommendation_agent.py` | Prescriptive runbook formulation, Priority 1-3 categorization, verification criteria, CLI automation commands. |
| `test_orchestrator.py` | Parallel agent execution, timeout safety, unhandled agent crash recovery, report file persistence. |
| `test_scenarios.py` | End-to-end diagnosis verification of all 8 synthetic scenarios against expected root causes. |
| `test_api.py` | FastAPI TestClient testing `/health`, `/api/scenarios`, `/api/diagnose`, `/api/telemetry/upload-csv`, `/api/reports`. |
| `test_csv_loader.py` | CSV parsing, fuzzy column header matching, numeric coercion, missing column warning handling. |
