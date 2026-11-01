# NetCoop AI — Agent Communication & Interoperability Specification

## 1. Overview & Philosophy

NetCoop AI enforces strict modularity and decoupling across all agents. Agents never import or directly depend on other agents' internal logic or state. Instead, all communication traverses a standardized, Pydantic-based JSON message contract.

---

## 2. Standardized Message Schema (`AgentMessage`)

Each message transmitted by any agent conforms to the `AgentMessage` model (`communication/models.py`):

```json
{
  "message_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "task_id": "TASK-A1B2C3D4",
  "agent_id": "performance_agent",
  "timestamp": "2026-10-31T09:30:00Z",
  "status": "SUCCESS",
  "findings": [
    {
      "finding_id": "FND-88B12CFA",
      "category": "PERFORMANCE",
      "title": "Link Bandwidth Saturation",
      "description": "Bandwidth utilization reached 96.5% (mean: 88.2%). Link congestion causing bufferbloat.",
      "severity": "CRITICAL",
      "affected_devices": ["core-router-01", "edge-switch-01"],
      "metrics": {
        "max_bw_util_pct": 96.5,
        "mean_bw_util_pct": 88.2
      }
    }
  ],
  "evidence": [
    {
      "metric_name": "bandwidth_util_pct",
      "observed_value": 96.5,
      "threshold": 80.0,
      "unit": "%",
      "device_id": "core-router-01",
      "details": "Bandwidth utilization peaked at 96.5%, exceeding 80.0% warning limit."
    }
  ],
  "confidence": 0.92,
  "errors": [],
  "metadata": {
    "agent_name": "Network Performance Specialist",
    "record_count": 15,
    "execution_time_ms": 14.2
  }
}
```

---

## 3. Schema Fields Breakdown

| Field | Type | Description |
| :--- | :--- | :--- |
| `message_id` | `UUID (str)` | Unique identifier for message tracking and deduplication. |
| `task_id` | `str` | Global correlation ID shared across all agents in a single diagnostic cycle. |
| `agent_id` | `str` | Name/identifier of publishing agent (`performance_agent`, `infrastructure_agent`, etc.). |
| `timestamp` | `datetime (ISO-8601)` | Timestamp when the message was generated in UTC. |
| `status` | `Enum (str)` | `SUCCESS`, `WARNING`, `ERROR`, `TIMEOUT`, `INSUFFICIENT_DATA`. |
| `findings` | `List[Finding]` | Semantic diagnostic conclusions with severity and affected devices. |
| `evidence` | `List[EvidenceItem]` | Quantitative metric breaches (observed value vs threshold). |
| `confidence`| `float [0.0 - 1.0]`| Clamped numerical confidence rating for the analysis. |
| `errors` | `List[str]` | Any execution anomalies, schema warnings, or degraded operations. |
| `metadata` | `Dict[str, Any]` | Agent-specific context (e.g. execution duration ms, candidate hypotheses). |

---

## 4. Message Validation & Error Envelope Handling

The protocol layer (`communication/protocol.py`) provides helper functions:
- `validate_message(data)`: Validates raw JSON string or Python dictionary against schema.
- `create_error_message(task_id, agent_id, error_desc, status)`: Creates compliant error messages when an agent fails or times out.
- `serialize_message(msg)`: Emits compact or indented JSON.
- `deserialize_message(json_str)`: Hydrates JSON into validated Pydantic models.
