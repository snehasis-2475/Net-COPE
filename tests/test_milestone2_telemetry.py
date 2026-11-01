from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import pytest

from communication.telemetry_generator import TelemetryGenerator
from communication.telemetry_ingestion import TelemetryIngestionService
from communication.telemetry_schema import (
    ConnectivityStatus,
    DHCPStatus,
    DNSStatus,
    DeviceStatus,
    DeviceType,
    TelemetryBatchSchema,
    TelemetryRecord,
)
from communication.telemetry_validator import TelemetryValidator


# ============================================================================
# 1. VALID TELEMETRY TESTS
# ============================================================================

def test_valid_telemetry_all_fields():
    """Test fully populated, valid telemetry record."""
    data = {
        "device_id": "core-router-01",
        "device_type": "router",
        "timestamp": "2026-10-31T12:00:00Z",
        "location": "DC-East-Rack-4",
        "interface_name": "TenGig0/1",
        "latency_ms": 15.5,
        "jitter_ms": 2.1,
        "packet_loss_percent": 0.5,
        "throughput_mbps": 850.0,
        "bandwidth_utilization_percent": 45.0,
        "cpu_utilization_percent": 35.0,
        "memory_utilization_percent": 55.0,
        "device_status": "active",
        "interface_errors": 0,
        "queue_drops": 0,
        "wifi_signal_dbm": -55.0,
        "dns_status": "success",
        "dhcp_status": "bound",
        "connectivity_status": "connected",
    }
    result = TelemetryValidator.validate_record(data)
    assert result.is_valid is True
    assert result.record is not None
    assert result.record.device_id == "core-router-01"
    assert result.record.latency_ms == 15.5
    assert result.record.packet_loss_percent == 0.5
    assert result.record.device_status == "active"
    assert len(result.errors) == 0


def test_valid_telemetry_minimal_fields():
    """Test telemetry record with only required fields (optional fields missing/None)."""
    data = {
        "device_id": "sensor-01",
        "timestamp": datetime.now(timezone.utc),
    }
    result = TelemetryValidator.validate_record(data)
    assert result.is_valid is True
    assert result.record is not None
    assert result.record.device_id == "sensor-01"
    assert result.record.latency_ms is None
    assert result.record.cpu_utilization_percent is None
    assert result.record.device_type == "generic"


def test_field_aliases_compatibility():
    """Test aliases (packet_loss_pct, cpu_util_pct, wifi_rssi_dbm) map cleanly."""
    data = {
        "device_id": "switch-01",
        "timestamp": "2026-10-31T12:00:00Z",
        "packet_loss_pct": 2.5,
        "bandwidth_util_pct": 78.0,
        "cpu_util_pct": 60.0,
        "memory_util_pct": 70.0,
        "wifi_rssi_dbm": -68.0,
        "dns_resolution_status": "success",
    }
    result = TelemetryValidator.validate_record(data)
    assert result.is_valid is True
    assert result.record.packet_loss_percent == 2.5
    assert result.record.bandwidth_utilization_percent == 78.0
    assert result.record.cpu_utilization_percent == 60.0
    assert result.record.wifi_signal_dbm == -68.0
    assert result.record.dns_status == "success"


# ============================================================================
# 2. REQUIRED IDENTIFICATION FIELDS VALIDATION
# ============================================================================

def test_missing_device_id():
    """Test validation fails when device_id is missing or empty."""
    # Missing key
    data1 = {"timestamp": "2026-10-31T12:00:00Z", "latency_ms": 10.0}
    res1 = TelemetryValidator.validate_record(data1)
    assert res1.is_valid is False
    assert any(e.field == "device_id" for e in res1.errors)

    # Empty string
    data2 = {"device_id": "", "timestamp": "2026-10-31T12:00:00Z"}
    res2 = TelemetryValidator.validate_record(data2)
    assert res2.is_valid is False
    assert any(e.field == "device_id" for e in res2.errors)

    # Whitespace only
    data3 = {"device_id": "   ", "timestamp": "2026-10-31T12:00:00Z"}
    res3 = TelemetryValidator.validate_record(data3)
    assert res3.is_valid is False


def test_missing_timestamp():
    """Test validation fails when timestamp is missing or empty."""
    data = {"device_id": "router-01", "latency_ms": 15.0}
    res = TelemetryValidator.validate_record(data)
    assert res.is_valid is False
    assert any(e.field == "timestamp" for e in res.errors)


def test_invalid_timestamp_formats():
    """Test validation fails with unparseable or corrupted timestamps."""
    invalid_timestamps = [
        "not-a-timestamp",
        "2026/99/99 99:99",
        "",
        "   ",
        {"date": "today"},
    ]
    for inv_ts in invalid_timestamps:
        data = {"device_id": "router-01", "timestamp": inv_ts}
        res = TelemetryValidator.validate_record(data)
        assert res.is_valid is False
        assert any("timestamp" in e.field for e in res.errors)


# ============================================================================
# 3. RANGE AND BOUNDS VALIDATION
# ============================================================================

def test_negative_numeric_metrics_rejected():
    """Negative latency, jitter, throughput, errors, queue drops must be rejected."""
    base = {"device_id": "router-01", "timestamp": "2026-10-31T12:00:00Z"}

    # Negative latency
    res_lat = TelemetryValidator.validate_record({**base, "latency_ms": -1.0})
    assert res_lat.is_valid is False
    assert any(e.field == "latency_ms" for e in res_lat.errors)

    # Negative jitter
    res_jit = TelemetryValidator.validate_record({**base, "jitter_ms": -0.5})
    assert res_jit.is_valid is False
    assert any(e.field == "jitter_ms" for e in res_jit.errors)

    # Negative throughput
    res_tp = TelemetryValidator.validate_record({**base, "throughput_mbps": -100.0})
    assert res_tp.is_valid is False
    assert any(e.field == "throughput_mbps" for e in res_tp.errors)

    # Negative errors
    res_err = TelemetryValidator.validate_record({**base, "interface_errors": -5})
    assert res_err.is_valid is False
    assert any(e.field == "interface_errors" for e in res_err.errors)

    # Negative queue drops
    res_drop = TelemetryValidator.validate_record({**base, "queue_drops": -1})
    assert res_drop.is_valid is False
    assert any(e.field == "queue_drops" for e in res_drop.errors)


def test_percentage_metrics_outside_0_to_100_rejected():
    """Packet loss, CPU, memory, bandwidth outside 0-100% must be rejected."""
    base = {"device_id": "router-01", "timestamp": "2026-10-31T12:00:00Z"}

    # Packet loss < 0 or > 100
    assert TelemetryValidator.validate_record({**base, "packet_loss_percent": -0.1}).is_valid is False
    assert TelemetryValidator.validate_record({**base, "packet_loss_percent": 100.1}).is_valid is False

    # CPU util < 0 or > 100
    assert TelemetryValidator.validate_record({**base, "cpu_utilization_percent": -5.0}).is_valid is False
    assert TelemetryValidator.validate_record({**base, "cpu_utilization_percent": 120.0}).is_valid is False

    # Memory util < 0 or > 100
    assert TelemetryValidator.validate_record({**base, "memory_utilization_percent": -1.0}).is_valid is False
    assert TelemetryValidator.validate_record({**base, "memory_utilization_percent": 101.0}).is_valid is False

    # Bandwidth util < 0 or > 100
    assert TelemetryValidator.validate_record({**base, "bandwidth_utilization_percent": -10.0}).is_valid is False
    assert TelemetryValidator.validate_record({**base, "bandwidth_utilization_percent": 105.0}).is_valid is False


def test_wifi_signal_bounds():
    """Wi-Fi signal must be within -120.0 dBm to 0.0 dBm."""
    base = {"device_id": "ap-01", "timestamp": "2026-10-31T12:00:00Z"}

    # Valid values
    assert TelemetryValidator.validate_record({**base, "wifi_signal_dbm": -55.0}).is_valid is True
    assert TelemetryValidator.validate_record({**base, "wifi_signal_dbm": -120.0}).is_valid is True
    assert TelemetryValidator.validate_record({**base, "wifi_signal_dbm": 0.0}).is_valid is True

    # Out of range
    assert TelemetryValidator.validate_record({**base, "wifi_signal_dbm": -125.0}).is_valid is False
    assert TelemetryValidator.validate_record({**base, "wifi_signal_dbm": 5.0}).is_valid is False


# ============================================================================
# 4. STATUS ENUMS AND DATA TYPES VALIDATION
# ============================================================================

def test_invalid_status_enums_rejected():
    """Invalid device, dns, dhcp, connectivity statuses must be rejected."""
    base = {"device_id": "node-01", "timestamp": "2026-10-31T12:00:00Z"}

    # Invalid device_status
    res_dev = TelemetryValidator.validate_record({**base, "device_status": "on_fire"})
    assert res_dev.is_valid is False
    assert any(e.field == "device_status" for e in res_dev.errors)

    # Invalid dns_status
    res_dns = TelemetryValidator.validate_record({**base, "dns_status": "magic_query"})
    assert res_dns.is_valid is False
    assert any(e.field == "dns_status" for e in res_dns.errors)

    # Invalid dhcp_status
    res_dhcp = TelemetryValidator.validate_record({**base, "dhcp_status": "borrowed"})
    assert res_dhcp.is_valid is False
    assert any(e.field == "dhcp_status" for e in res_dhcp.errors)

    # Invalid connectivity_status
    res_conn = TelemetryValidator.validate_record({**base, "connectivity_status": "semi_connected"})
    assert res_conn.is_valid is False
    assert any(e.field == "connectivity_status" for e in res_conn.errors)


def test_invalid_data_types():
    """Booleans passed for numeric metrics or unparseable strings must fail validation."""
    base = {"device_id": "node-01", "timestamp": "2026-10-31T12:00:00Z"}

    # Boolean passed for latency
    res_bool = TelemetryValidator.validate_record({**base, "latency_ms": True})
    assert res_bool.is_valid is False
    assert any(e.field == "latency_ms" for e in res_bool.errors)

    # String passed for CPU
    res_str = TelemetryValidator.validate_record({**base, "cpu_utilization_percent": "very_high"})
    assert res_str.is_valid is False
    assert any(e.field == "cpu_utilization_percent" for e in res_str.errors)


# ============================================================================
# 5. INGESTION SERVICE TESTS
# ============================================================================

def test_ingestion_single_json_record():
    service = TelemetryIngestionService()
    json_str = json.dumps({
        "device_id": "r1",
        "timestamp": "2026-10-31T12:00:00Z",
        "latency_ms": 12.0,
    })
    res = service.ingest_json_record(json_str)
    assert res.is_fully_valid is True
    assert res.valid_count == 1
    assert res.error_count == 0
    assert res.valid_records[0].device_id == "r1"


def test_ingestion_json_list():
    service = TelemetryIngestionService()
    items = [
        {"device_id": "r1", "timestamp": "2026-10-31T12:00:00Z", "latency_ms": 12.0},
        {"device_id": "r2", "timestamp": "2026-10-31T12:00:00Z", "latency_ms": 14.5},
    ]
    res = service.ingest_json_list(items)
    assert res.is_fully_valid is True
    assert res.valid_count == 2
    assert res.error_count == 0


def test_ingestion_csv():
    service = TelemetryIngestionService()
    csv_text = (
        "device_id,timestamp,latency_ms,packet_loss_percent,cpu_utilization_percent\n"
        "router-01,2026-10-31T12:00:00Z,15.2,0.0,35.0\n"
        "router-02,2026-10-31T12:00:00Z,18.4,0.0,42.0\n"
    )
    res = service.ingest_csv(csv_text)
    assert res.is_fully_valid is True
    assert res.valid_count == 2
    assert res.error_count == 0
    df = res.to_dataframe()
    assert len(df) == 2
    assert "device_id" in df.columns


def test_ingestion_csv_fuzzy_headers():
    service = TelemetryIngestionService()
    csv_text = (
        "Host,Timestamp,RTT,Loss,Processor Util\n"
        "core-node,2026-10-31T12:00:00Z,12.5,0.0,55.0\n"
    )
    res = service.ingest_csv(csv_text)
    assert res.is_fully_valid is True
    assert res.valid_count == 1
    assert res.valid_records[0].device_id == "core-node"
    assert res.valid_records[0].latency_ms == 12.5
    assert res.valid_records[0].cpu_utilization_percent == 55.0


def test_ingestion_batch_schema():
    service = TelemetryIngestionService()
    rec = TelemetryRecord(
        device_id="dev-01",
        timestamp=datetime.now(timezone.utc),
        latency_ms=10.0,
    )
    batch = TelemetryBatchSchema(records=[rec], source="api_test")
    res = service.ingest_batch(batch)
    assert res.is_fully_valid is True
    assert res.valid_count == 1


# ============================================================================
# 6. PARTIAL BATCH FAILURE ISOLATION TESTS
# ============================================================================

def test_partial_batch_failures_isolation():
    """
    Ensure one invalid record does NOT silently corrupt the remaining valid records.
    Batch contains 4 records: 2 valid, 2 invalid.
    """
    service = TelemetryIngestionService()
    batch_data = [
        # 1. Valid
        {"device_id": "r1", "timestamp": "2026-10-31T12:00:00Z", "latency_ms": 12.0},
        # 2. Invalid (Negative latency)
        {"device_id": "r2", "timestamp": "2026-10-31T12:00:00Z", "latency_ms": -50.0},
        # 3. Valid
        {"device_id": "r3", "timestamp": "2026-10-31T12:00:00Z", "latency_ms": 15.0},
        # 4. Invalid (Missing device_id)
        {"device_id": "", "timestamp": "2026-10-31T12:00:00Z", "latency_ms": 20.0},
    ]

    res = service.ingest_json_list(batch_data)
    assert res.total_records == 4
    assert res.valid_count == 2
    assert res.error_count >= 2
    assert res.has_partial_failures is True

    # Check preserved valid devices
    valid_ids = [r.device_id for r in res.valid_records]
    assert valid_ids == ["r1", "r3"]

    # Check error reports
    error_fields = [e.field for e in res.validation_errors]
    assert "latency_ms" in error_fields
    assert "device_id" in error_fields


# ============================================================================
# 7. ALL SYNTHETIC SCENARIOS GENERATION & INTEGRITY TESTS
# ============================================================================

@pytest.mark.parametrize("scenario_name", [
    "normal",
    "congestion",
    "weak_wifi",
    "interface_failure",
    "dns_failure",
    "dhcp_failure",
    "infrastructure_overload",
])
def test_all_synthetic_scenarios_generate_valid_telemetry(scenario_name: str):
    """Verify each synthetic scenario generates valid TelemetryRecords adhering to schema."""
    records = TelemetryGenerator.generate(scenario_name, count=10)
    assert len(records) > 0

    # Ensure all generated records pass TelemetryValidator
    for rec in records:
        val_res = TelemetryValidator.validate_record(rec)
        assert val_res.is_valid is True
        assert val_res.record is not None
        assert val_res.record.device_id != ""
        assert val_res.record.timestamp is not None


def test_scenario_files_persisted_on_disk():
    """Verify that both JSON and CSV files exist in data/scenarios/ for each scenario."""
    scenarios = TelemetryGenerator.SUPPORTED_SCENARIOS
    scenarios_dir = Path("data") / "scenarios"
    assert scenarios_dir.exists()

    for sc in scenarios:
        json_file = scenarios_dir / f"{sc}.json"
        csv_file = scenarios_dir / f"{sc}.csv"
        assert json_file.exists(), f"Missing scenario JSON: {json_file}"
        assert csv_file.exists(), f"Missing scenario CSV: {csv_file}"
        assert json_file.stat().st_size > 0
        assert csv_file.stat().st_size > 0
