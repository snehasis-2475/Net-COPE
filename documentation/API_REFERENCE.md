# NetCoop AI — FastAPI REST API Reference

The NetCoop AI backend exposes an asynchronous RESTful API via FastAPI with automated interactive OpenAPI documentation available at `/docs`.

Base URL: `http://localhost:8000`

---

## 1. System Endpoints

### `GET /health`
Returns system operational health, version, and loaded specialized agents.

**Response (200 OK):**
```json
{
  "status": "healthy",
  "service": "NetCoop AI Multi-Agent Diagnostic Engine",
  "version": "1.0.0",
  "timestamp": "2026-10-31T09:30:00Z",
  "active_agents": [
    "performance_agent",
    "infrastructure_agent",
    "connectivity_agent",
    "correlation_agent",
    "recommendation_agent"
  ]
}
```

---

## 2. Scenario Endpoints

### `GET /api/scenarios`
Lists all built-in reproducible network scenarios.

**Response (200 OK):**
```json
{
  "scenarios": [
    {
      "scenario_id": "normal",
      "title": "1. Normal Network Operation",
      "description": "Baseline nominal telemetry. Low latency (<15ms), 0% loss, healthy CPU and memory.",
      "expected_root_cause": "Nominal Network Operation"
    },
    {
      "scenario_id": "congestion",
      "title": "2. Network Congestion & Bufferbloat",
      "description": "Transit link saturated (>94% bandwidth), queue drops, severe RTT latency and jitter spikes.",
      "expected_root_cause": "Network Bandwidth Congestion & Bufferbloat"
    }
  ],
  "total": 8
}
```

### `GET /api/scenarios/{scenario_id}`
Returns metadata and synthetic time-series telemetry dataset for a specific scenario.

**Parameters:**
- `scenario_id`: `normal`, `congestion`, `weak_wifi`, `interface_failure`, `dns_failure`, `dhcp_failure`, `infrastructure_overload`, `invalid_telemetry`.

---

## 3. Telemetry Ingest Endpoints

### `POST /api/telemetry/submit`
Validates and stages raw JSON telemetry batches.

**Request Body:**
```json
{
  "batch_id": "optional-uuid",
  "scenario_name": "custom",
  "records": [
    {
      "device_id": "core-router-01",
      "latency_ms": 15.2,
      "cpu_util_pct": 35.0
    }
  ]
}
```

### `POST /api/telemetry/upload-csv`
Accepts multipart form file upload of a `.csv` telemetry file. Automatically applies fuzzy column matching and numeric cleaning.

---

## 4. Diagnosis Endpoints

### `POST /api/diagnose`
Triggers full multi-agent diagnostic execution.

**Request Body (Option A - by Scenario):**
```json
{
  "scenario_id": "congestion"
}
```

**Request Body (Option B - by Raw Telemetry):**
```json
{
  "telemetry": [
    {
      "device_id": "core-01",
      "latency_ms": 190.0,
      "bandwidth_util_pct": 96.0
    }
  ]
}
```

**Response (200 OK):**
Returns complete `DiagnosticReport` JSON object containing `report_id`, `overall_network_health`, `probable_root_cause`, `alternative_causes`, `supporting_evidence`, `individual_agent_findings`, and `recommended_corrective_actions`.

---

## 5. Report Retrieval Endpoints

### `GET /api/reports`
Lists all persisted diagnostic reports (ordered most recent first).
- Query Parameter: `limit` (default: 20).

### `GET /api/reports/{report_id}`
Retrieves full JSON diagnostic report by ID (e.g., `REP-A1B2C3D4`).
