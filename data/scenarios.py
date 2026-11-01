from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List
import pandas as pd

from communication.models import NetworkTelemetryRecord, TelemetryBatch

SAMPLE_DIR = Path(__file__).resolve().parent / "samples"
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)



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

def generate_scenario_data(scenario_id: str) -> List[Dict[str, Any]]:
    """Generates synthetic telemetry records for the specified network scenario."""
    now = datetime.now(timezone.utc)
    scenario_id = scenario_id.lower().replace("-", "_")

    if scenario_id == "normal":
        return _generate_normal(now)
    elif scenario_id == "congestion":
        return _generate_congestion(now)
    elif scenario_id == "weak_wifi":
        return _generate_weak_wifi(now)
    elif scenario_id == "interface_failure":
        return _generate_interface_failure(now)
    elif scenario_id == "dns_failure":
        return _generate_dns_failure(now)
    elif scenario_id == "dhcp_failure":
        return _generate_dhcp_failure(now)
    elif scenario_id == "infrastructure_overload":
        return _generate_infra_overload(now)
    elif scenario_id == "invalid_telemetry":
        return _generate_invalid(now)
    elif scenario_id in ("organizer_mock", "organizer_benchmark"):
        return _load_organizer_mock()
    else:
        raise ValueError(f"Unknown scenario ID: {scenario_id}")


def _generate_normal(base_time: datetime) -> List[Dict[str, Any]]:
    records = []
    devices = [("core-router-01", "router"), ("edge-switch-01", "switch"), ("ap-floor1", "ap"), ("workstation-04", "endpoint")]
    for t in range(12):
        ts = (base_time - timedelta(seconds=(12 - t) * 10)).isoformat()
        for dev, dev_type in devices:
            records.append({
                "timestamp": ts,
                "device_id": dev,
                "device_type": dev_type,
                "latency_ms": round(12.0 + (t % 3) * 1.5, 1),
                "jitter_ms": round(1.2 + (t % 2) * 0.4, 1),
                "packet_loss_pct": 0.0,
                "throughput_mbps": round(450.0 + (t % 4) * 20.0, 1),
                "bandwidth_util_pct": round(32.0 + (t % 5) * 2.0, 1),
                "device_availability": 100.0,
                "cpu_util_pct": round(24.0 + (t % 4) * 2.0, 1),
                "memory_util_pct": 42.0,
                "interface_status": "up",
                "interface_errors": 0,
                "queue_drops": 0,
                "dns_resolution_status": "success",
                "dns_latency_ms": round(8.5 + (t % 2) * 1.0, 1),
                "dhcp_status": "bound",
                "wifi_rssi_dbm": -52.0 if dev_type in ["ap", "endpoint"] else None,
                "wifi_snr_db": 34.0 if dev_type in ["ap", "endpoint"] else None,
                "connectivity_status": "connected",
            })
    return records


def _generate_congestion(base_time: datetime) -> List[Dict[str, Any]]:
    records = []
    devices = [("core-router-01", "router"), ("edge-switch-01", "switch"), ("workstation-04", "endpoint")]
    for t in range(15):
        ts = (base_time - timedelta(seconds=(15 - t) * 10)).isoformat()
        congestion_active = t >= 4
        bw = round(94.5 + (t % 3) * 1.5, 1) if congestion_active else 45.0
        lat = round(175.0 + (t % 4) * 15.0, 1) if congestion_active else 15.0
        jit = round(38.0 + (t % 3) * 4.0, 1) if congestion_active else 2.0
        loss = round(4.8 + (t % 3) * 0.8, 1) if congestion_active else 0.0
        drops = int(140 + t * 25) if congestion_active else 0

        for dev, dev_type in devices:
            records.append({
                "timestamp": ts,
                "device_id": dev,
                "device_type": dev_type,
                "latency_ms": lat,
                "jitter_ms": jit,
                "packet_loss_pct": loss,
                "throughput_mbps": 890.0 if dev == "core-router-01" else 95.0,
                "bandwidth_util_pct": bw if dev in ["core-router-01", "edge-switch-01"] else 60.0,
                "device_availability": 100.0,
                "cpu_util_pct": 52.0,  # CPU is moderate, proving network link congestion rather than CPU peg
                "memory_util_pct": 48.0,
                "interface_status": "up",
                "interface_errors": 0,
                "queue_drops": drops if dev in ["core-router-01", "edge-switch-01"] else 0,
                "dns_resolution_status": "success",
                "dns_latency_ms": 18.0 if not congestion_active else 45.0,
                "dhcp_status": "bound",
                "wifi_rssi_dbm": None,
                "wifi_snr_db": None,
                "connectivity_status": "degraded" if congestion_active else "connected",
            })
    return records


def _generate_weak_wifi(base_time: datetime) -> List[Dict[str, Any]]:
    records = []
    for t in range(12):
        ts = (base_time - timedelta(seconds=(12 - t) * 10)).isoformat()
        # Core router is perfectly fine
        records.append({
            "timestamp": ts,
            "device_id": "core-router-01",
            "device_type": "router",
            "latency_ms": 11.0,
            "jitter_ms": 1.1,
            "packet_loss_pct": 0.0,
            "throughput_mbps": 600.0,
            "bandwidth_util_pct": 28.0,
            "device_availability": 100.0,
            "cpu_util_pct": 22.0,
            "memory_util_pct": 39.0,
            "interface_status": "up",
            "interface_errors": 0,
            "queue_drops": 0,
            "dns_resolution_status": "success",
            "dns_latency_ms": 7.0,
            "dhcp_status": "bound",
            "wifi_rssi_dbm": None,
            "wifi_snr_db": None,
            "connectivity_status": "connected",
        })
        # Wireless client in far meeting room is attenuated
        records.append({
            "timestamp": ts,
            "device_id": "workstation-conf-room",
            "device_type": "endpoint",
            "latency_ms": round(85.0 + (t % 4) * 12.0, 1),
            "jitter_ms": round(26.0 + (t % 3) * 5.0, 1),
            "packet_loss_pct": round(9.5 + (t % 3) * 2.0, 1),
            "throughput_mbps": 12.0,
            "bandwidth_util_pct": 18.0,
            "device_availability": 100.0,
            "cpu_util_pct": 15.0,
            "memory_util_pct": 32.0,
            "interface_status": "up",
            "interface_errors": 0,
            "queue_drops": 0,
            "dns_resolution_status": "success",
            "dns_latency_ms": 42.0,
            "dhcp_status": "bound",
            "wifi_rssi_dbm": round(-85.0 - (t % 3) * 1.5, 1),  # Severe signal attenuation
            "wifi_snr_db": round(11.0 - (t % 2) * 1.0, 1),      # Low SNR
            "connectivity_status": "degraded",
        })
    return records


def _generate_interface_failure(base_time: datetime) -> List[Dict[str, Any]]:
    records = []
    for t in range(12):
        ts = (base_time - timedelta(seconds=(12 - t) * 10)).isoformat()
        is_down = t >= 4
        records.append({
            "timestamp": ts,
            "device_id": "edge-switch-02",
            "device_type": "switch",
            "latency_ms": 180.0 if is_down else 14.0,
            "jitter_ms": 40.0 if is_down else 1.5,
            "packet_loss_pct": 75.0 if is_down else 0.0,
            "throughput_mbps": 0.0 if is_down else 320.0,
            "bandwidth_util_pct": 0.0 if is_down else 35.0,
            "device_availability": 50.0 if is_down else 100.0,
            "cpu_util_pct": 28.0,
            "memory_util_pct": 44.0,
            "interface_status": "flapping" if t in [4, 5, 8] else ("down" if is_down else "up"),
            "interface_errors": int(120 + t * 45) if is_down else 0,
            "queue_drops": 0,
            "dns_resolution_status": "timeout" if is_down else "success",
            "dns_latency_ms": 500.0 if is_down else 10.0,
            "dhcp_status": "failed" if is_down else "bound",
            "wifi_rssi_dbm": None,
            "wifi_snr_db": None,
            "connectivity_status": "disconnected" if is_down else "connected",
        })
    return records


def _generate_dns_failure(base_time: datetime) -> List[Dict[str, Any]]:
    records = []
    devices = ["workstation-01", "workstation-02", "server-app-01"]
    for t in range(10):
        ts = (base_time - timedelta(seconds=(10 - t) * 10)).isoformat()
        dns_outage = t >= 3
        for dev in devices:
            records.append({
                "timestamp": ts,
                "device_id": dev,
                "device_type": "endpoint",
                "latency_ms": 14.0,  # Ping by IP is fast!
                "jitter_ms": 1.2,
                "packet_loss_pct": 0.0,  # No transmission loss
                "throughput_mbps": 240.0,
                "bandwidth_util_pct": 25.0,
                "device_availability": 100.0,
                "cpu_util_pct": 20.0,
                "memory_util_pct": 35.0,
                "interface_status": "up",
                "interface_errors": 0,
                "queue_drops": 0,
                "dns_resolution_status": "servfail" if dns_outage and t % 2 == 0 else ("timeout" if dns_outage else "success"),
                "dns_latency_ms": 1250.0 if dns_outage else 9.0,
                "dhcp_status": "bound",
                "wifi_rssi_dbm": -56.0,
                "wifi_snr_db": 30.0,
                "connectivity_status": "degraded" if dns_outage else "connected",
            })
    return records


def _generate_dhcp_failure(base_time: datetime) -> List[Dict[str, Any]]:
    records = []
    devices = ["finance-laptop-07", "sales-laptop-11", "guest-device-22"]
    for t in range(10):
        ts = (base_time - timedelta(seconds=(10 - t) * 10)).isoformat()
        dhcp_exhausted = t >= 3
        for dev in devices:
            records.append({
                "timestamp": ts,
                "device_id": dev,
                "device_type": "endpoint",
                "latency_ms": 999.0 if dhcp_exhausted else 15.0,
                "jitter_ms": 0.0 if dhcp_exhausted else 2.0,
                "packet_loss_pct": 100.0 if dhcp_exhausted else 0.0,
                "throughput_mbps": 0.0 if dhcp_exhausted else 50.0,
                "bandwidth_util_pct": 0.0 if dhcp_exhausted else 10.0,
                "device_availability": 100.0,
                "cpu_util_pct": 15.0,
                "memory_util_pct": 30.0,
                "interface_status": "up",  # Interface is connected to AP
                "interface_errors": 0,
                "queue_drops": 0,
                "dns_resolution_status": "timeout" if dhcp_exhausted else "success",
                "dns_latency_ms": 0.0 if dhcp_exhausted else 10.0,
                "dhcp_status": "exhausted" if dhcp_exhausted else "bound",
                "wifi_rssi_dbm": -58.0,  # RF link is excellent!
                "wifi_snr_db": 32.0,
                "connectivity_status": "disconnected" if dhcp_exhausted else "connected",
            })
    return records


def _generate_infra_overload(base_time: datetime) -> List[Dict[str, Any]]:
    records = []
    for t in range(12):
        ts = (base_time - timedelta(seconds=(12 - t) * 10)).isoformat()
        is_pegged = t >= 3
        records.append({
            "timestamp": ts,
            "device_id": "core-router-01",
            "device_type": "router",
            "latency_ms": round(190.0 + (t % 3) * 20.0, 1) if is_pegged else 12.0,
            "jitter_ms": round(42.0 + (t % 3) * 6.0, 1) if is_pegged else 1.5,
            "packet_loss_pct": 6.5 if is_pegged else 0.0,
            "throughput_mbps": 110.0 if is_pegged else 850.0,
            "bandwidth_util_pct": 55.0,  # Bandwidth not maxed, ruling out transit line congestion
            "device_availability": 88.0 if is_pegged else 100.0,
            "cpu_util_pct": round(96.0 + (t % 3) * 1.5, 1) if is_pegged else 30.0,  # Critical CPU
            "memory_util_pct": round(93.0 + (t % 2) * 1.5, 1) if is_pegged else 45.0,  # Critical RAM
            "interface_status": "up",
            "interface_errors": 0,
            "queue_drops": int(320 + t * 40) if is_pegged else 0,
            "dns_resolution_status": "success",
            "dns_latency_ms": 65.0 if is_pegged else 8.0,
            "dhcp_status": "bound",
            "wifi_rssi_dbm": None,
            "wifi_snr_db": None,
            "connectivity_status": "degraded" if is_pegged else "connected",
        })
    return records


def _generate_invalid(base_time: datetime) -> List[Dict[str, Any]]:
    """Invalid telemetry records with malformed values and missing keys."""
    return [
        {"timestamp": "corrupt-date", "device_id": "", "latency_ms": -500.0, "packet_loss_pct": 350.0},
        {"timestamp": None, "device_id": None, "cpu_util_pct": 200.0},
        {"random_garbage": "malformed_json_field", "value": "null"},
        {"device_id": "router-x", "interface_status": "invalid_status_enum", "bandwidth_util_pct": -99.0},
    ]


SCENARIO_METADATA = {
    "normal": {
        "title": "1. Normal Network Operation",
        "description": "Baseline nominal telemetry. Low latency (<15ms), 0% loss, healthy CPU and memory.",
        "expected_root_cause": "Nominal Network Operation",
    },
    "congestion": {
        "title": "2. Network Congestion & Bufferbloat",
        "description": "Transit link saturated (>94% bandwidth), queue drops, severe RTT latency and jitter spikes.",
        "expected_root_cause": "Network Bandwidth Congestion & Bufferbloat",
    },
    "weak_wifi": {
        "title": "3. Weak Wi-Fi RF Signal",
        "description": "Meeting room workstation experiencing high attenuation (-86 dBm RSSI) and localized packet loss, while core network is pristine.",
        "expected_root_cause": "Wireless RF Attenuation / Weak Wi-Fi Coverage",
    },
    "interface_failure": {
        "title": "4. Interface / Cable Failure",
        "description": "Edge switch port flapping/down with accumulating CRC frame errors and zero throughput.",
        "expected_root_cause": "Physical Interface / Cable Failure",
    },
    "dns_failure": {
        "title": "5. DNS Resolution Failure",
        "description": "Upstream nameserver timeouts and servfail errors. Raw IP ping and link layer remain operational.",
        "expected_root_cause": "DNS Resolver Outage or Misconfiguration",
    },
    "dhcp_failure": {
        "title": "6. DHCP Pool Exhaustion",
        "description": "Clients connected to Wi-Fi AP cannot obtain IP addresses due to scope exhaustion.",
        "expected_root_cause": "DHCP Service Failure / Scope Exhaustion",
    },
    "infrastructure_overload": {
        "title": "7. Infrastructure Overload (CPU/RAM)",
        "description": "Core router CPU at 98% and RAM at 94% with internal queue drops and process delay.",
        "expected_root_cause": "Device Hardware / Compute Resource Overload",
    },
    "invalid_telemetry": {
        "title": "8. Invalid Telemetry Dataset",
        "description": "Corrupt telemetry with missing IDs, negative latencies, and out-of-range values testing validation resilience.",
        "expected_root_cause": "Invalid or Empty Telemetry",
    },
    "organizer_mock": {
        "title": "9. Official Organizer Benchmark (Campus Switches)",
        "description": "Official 100-record hackathon test dataset with 10 campus switches (SW_CAMPUS_1 to SW_CAMPUS_10) experiencing progressive bufferbloat, queue drops, and interface saturation.",
        "expected_root_cause": "Network Bandwidth Congestion & Bufferbloat",
    },
}


def dump_all_scenario_csvs():
    """Generates and writes CSV sample files to data/samples/ for instant download/testing."""
    for sc_id in SCENARIO_METADATA.keys():
        data = generate_scenario_data(sc_id)
        df = pd.DataFrame(data)
        file_path = SAMPLE_DIR / f"{sc_id}.csv"
        df.to_csv(file_path, index=False)


# Auto-generate CSV files upon loading
try:
    dump_all_scenario_csvs()
except Exception:
    pass
