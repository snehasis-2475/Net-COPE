from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from .telemetry_schema import (
    ConnectivityStatus,
    DHCPStatus,
    DNSStatus,
    DeviceStatus,
    DeviceType,
    TelemetryRecord,
)

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "data" / "scenarios"
SCENARIOS_DIR.mkdir(parents=True, exist_ok=True)


class TelemetryGenerator:
    """
    Synthetic telemetry generator producing realistic multi-device, multi-metric network telemetry.
    Supports all required diagnostic scenarios with distinctive behavioral signatures.
    """

    SUPPORTED_SCENARIOS = [
        "normal",
        "congestion",
        "weak_wifi",
        "interface_failure",
        "dns_failure",
        "dhcp_failure",
        "infrastructure_overload",
    ]

    @classmethod
    def generate(
        cls,
        scenario: str,
        count: int = 12,
        base_time: Optional[datetime] = None,
    ) -> List[TelemetryRecord]:
        """
        Generates a sequence of validated TelemetryRecords for the requested scenario.
        """
        sc = scenario.strip().lower().replace("-", "_")
        if sc not in cls.SUPPORTED_SCENARIOS:
            raise ValueError(f"Unknown scenario '{scenario}'. Allowed: {cls.SUPPORTED_SCENARIOS}")

        base_dt = base_time or datetime.now(timezone.utc)

        generator_map = {
            "normal": cls._generate_normal,
            "congestion": cls._generate_congestion,
            "weak_wifi": cls._generate_weak_wifi,
            "interface_failure": cls._generate_interface_failure,
            "dns_failure": cls._generate_dns_failure,
            "dhcp_failure": cls._generate_dhcp_failure,
            "infrastructure_overload": cls._generate_infrastructure_overload,
        }

        records_data = generator_map[sc](count, base_dt)
        return [TelemetryRecord.model_validate(r) for r in records_data]

    @classmethod
    def _generate_normal(cls, count: int, base_dt: datetime) -> List[Dict[str, Any]]:
        records = []
        devices = [
            ("core-router-01", "router", "DC-East", "TenGig0/1"),
            ("dist-switch-01", "switch", "Building-A", "GigabitEthernet1/0/1"),
            ("ap-floor2", "access_point", "Floor-2", "wlan0"),
            ("workstation-14", "endpoint", "Office-204", "eth0"),
        ]
        for t in range(count):
            ts = base_dt - timedelta(seconds=(count - t) * 10)
            for dev_id, dev_type, loc, if_name in devices:
                is_wifi = dev_type in ["access_point", "endpoint"]
                records.append({
                    "device_id": dev_id,
                    "device_type": dev_type,
                    "timestamp": ts,
                    "location": loc,
                    "interface_name": if_name,
                    "latency_ms": round(11.0 + (t % 3) * 1.5, 1),
                    "jitter_ms": round(1.2 + (t % 2) * 0.4, 1),
                    "packet_loss_percent": 0.0,
                    "throughput_mbps": round(420.0 + (t % 4) * 25.0, 1) if dev_type != "endpoint" else 85.0,
                    "bandwidth_utilization_percent": round(28.0 + (t % 5) * 2.0, 1),
                    "cpu_utilization_percent": round(22.0 + (t % 4) * 2.0, 1),
                    "memory_utilization_percent": 41.0,
                    "device_status": DeviceStatus.ACTIVE.value,
                    "interface_errors": 0,
                    "queue_drops": 0,
                    "wifi_signal_dbm": -52.0 if is_wifi else None,
                    "dns_status": DNSStatus.SUCCESS.value,
                    "dhcp_status": DHCPStatus.BOUND.value,
                    "connectivity_status": ConnectivityStatus.CONNECTED.value,
                })
        return records

    @classmethod
    def _generate_congestion(cls, count: int, base_dt: datetime) -> List[Dict[str, Any]]:
        records = []
        devices = [
            ("core-router-01", "router", "DC-East", "TenGig0/1"),
            ("dist-switch-01", "switch", "Building-A", "GigabitEthernet1/0/1"),
            ("workstation-14", "endpoint", "Office-204", "eth0"),
        ]
        for t in range(count):
            ts = base_dt - timedelta(seconds=(count - t) * 10)
            congested = t >= 3
            bw = round(94.0 + (t % 3) * 1.8, 1) if congested else 42.0
            lat = round(170.0 + (t % 4) * 18.0, 1) if congested else 14.0
            jit = round(36.0 + (t % 3) * 5.0, 1) if congested else 2.0
            loss = round(4.5 + (t % 3) * 0.9, 1) if congested else 0.0
            drops = int(120 + t * 25) if congested else 0

            for dev_id, dev_type, loc, if_name in devices:
                records.append({
                    "device_id": dev_id,
                    "device_type": dev_type,
                    "timestamp": ts,
                    "location": loc,
                    "interface_name": if_name,
                    "latency_ms": lat,
                    "jitter_ms": jit,
                    "packet_loss_percent": loss,
                    "throughput_mbps": 910.0 if dev_type == "router" else 95.0,
                    "bandwidth_utilization_percent": bw if dev_type in ["router", "switch"] else 55.0,
                    "cpu_utilization_percent": 50.0,  # moderate CPU confirms transit line congestion
                    "memory_utilization_percent": 48.0,
                    "device_status": DeviceStatus.DEGRADED.value if congested else DeviceStatus.ACTIVE.value,
                    "interface_errors": 0,
                    "queue_drops": drops if dev_type in ["router", "switch"] else 0,
                    "wifi_signal_dbm": None,
                    "dns_status": DNSStatus.SUCCESS.value,
                    "dhcp_status": DHCPStatus.BOUND.value,
                    "connectivity_status": ConnectivityStatus.DEGRADED.value if congested else ConnectivityStatus.CONNECTED.value,
                })
        return records

    @classmethod
    def _generate_weak_wifi(cls, count: int, base_dt: datetime) -> List[Dict[str, Any]]:
        records = []
        for t in range(count):
            ts = base_dt - timedelta(seconds=(count - t) * 10)
            # Healthy Core Switch
            records.append({
                "device_id": "core-router-01",
                "device_type": "router",
                "timestamp": ts,
                "location": "DC-East",
                "interface_name": "TenGig0/1",
                "latency_ms": 12.0,
                "jitter_ms": 1.2,
                "packet_loss_percent": 0.0,
                "throughput_mbps": 650.0,
                "bandwidth_utilization_percent": 25.0,
                "cpu_utilization_percent": 20.0,
                "memory_utilization_percent": 38.0,
                "device_status": DeviceStatus.ACTIVE.value,
                "interface_errors": 0,
                "queue_drops": 0,
                "wifi_signal_dbm": None,
                "dns_status": DNSStatus.SUCCESS.value,
                "dhcp_status": DHCPStatus.BOUND.value,
                "connectivity_status": ConnectivityStatus.CONNECTED.value,
            })
            # Distant Wi-Fi endpoint suffering attenuation
            records.append({
                "device_id": "workstation-conf-room",
                "device_type": "endpoint",
                "timestamp": ts,
                "location": "Boardroom-West",
                "interface_name": "wlan0",
                "latency_ms": round(82.0 + (t % 4) * 14.0, 1),
                "jitter_ms": round(28.0 + (t % 3) * 6.0, 1),
                "packet_loss_percent": round(11.0 + (t % 3) * 2.5, 1),
                "throughput_mbps": 8.5,
                "bandwidth_utilization_percent": 15.0,
                "cpu_utilization_percent": 14.0,
                "memory_utilization_percent": 30.0,
                "device_status": DeviceStatus.DEGRADED.value,
                "interface_errors": 0,
                "queue_drops": 0,
                "wifi_signal_dbm": round(-86.0 - (t % 3) * 2.0, 1),  # Attenuated signal
                "dns_status": DNSStatus.SUCCESS.value,
                "dhcp_status": DHCPStatus.BOUND.value,
                "connectivity_status": ConnectivityStatus.DEGRADED.value,
            })
        return records

    @classmethod
    def _generate_interface_failure(cls, count: int, base_dt: datetime) -> List[Dict[str, Any]]:
        records = []
        for t in range(count):
            ts = base_dt - timedelta(seconds=(count - t) * 10)
            failed = t >= 3
            records.append({
                "device_id": "edge-switch-02",
                "device_type": "switch",
                "timestamp": ts,
                "location": "Warehouse-B",
                "interface_name": "GigabitEthernet0/24",
                "latency_ms": 190.0 if failed else 13.0,
                "jitter_ms": 45.0 if failed else 1.8,
                "packet_loss_percent": 80.0 if failed else 0.0,
                "throughput_mbps": 0.0 if failed else 280.0,
                "bandwidth_utilization_percent": 0.0 if failed else 32.0,
                "cpu_utilization_percent": 26.0,
                "memory_utilization_percent": 42.0,
                "device_status": DeviceStatus.DOWN.value if failed else DeviceStatus.ACTIVE.value,
                "interface_errors": int(150 + t * 50) if failed else 0,  # Rapidly incrementing CRC errors
                "queue_drops": 0,
                "wifi_signal_dbm": None,
                "dns_status": DNSStatus.TIMEOUT.value if failed else DNSStatus.SUCCESS.value,
                "dhcp_status": DHCPStatus.FAILED.value if failed else DHCPStatus.BOUND.value,
                "connectivity_status": ConnectivityStatus.DISCONNECTED.value if failed else ConnectivityStatus.CONNECTED.value,
            })
        return records

    @classmethod
    def _generate_dns_failure(cls, count: int, base_dt: datetime) -> List[Dict[str, Any]]:
        records = []
        devices = [
            ("workstation-01", "endpoint", "Sales-Wing", "eth0"),
            ("workstation-02", "endpoint", "HR-Dept", "eth0"),
            ("app-server-01", "server", "DC-East", "eth0"),
        ]
        for t in range(count):
            ts = base_dt - timedelta(seconds=(count - t) * 10)
            dns_failed = t >= 2
            for dev_id, dev_type, loc, if_name in devices:
                records.append({
                    "device_id": dev_id,
                    "device_type": dev_type,
                    "timestamp": ts,
                    "location": loc,
                    "interface_name": if_name,
                    "latency_ms": 12.5,  # IP-level ping remains fast
                    "jitter_ms": 1.1,
                    "packet_loss_percent": 0.0,  # Zero packet loss
                    "throughput_mbps": 210.0,
                    "bandwidth_utilization_percent": 22.0,
                    "cpu_utilization_percent": 18.0,
                    "memory_utilization_percent": 34.0,
                    "device_status": DeviceStatus.ACTIVE.value,
                    "interface_errors": 0,
                    "queue_drops": 0,
                    "wifi_signal_dbm": -55.0 if dev_type == "endpoint" else None,
                    "dns_status": DNSStatus.SERVFAIL.value if dns_failed and t % 2 == 0 else (DNSStatus.TIMEOUT.value if dns_failed else DNSStatus.SUCCESS.value),
                    "dhcp_status": DHCPStatus.BOUND.value,
                    "connectivity_status": ConnectivityStatus.DEGRADED.value if dns_failed else ConnectivityStatus.CONNECTED.value,
                })
        return records

    @classmethod
    def _generate_dhcp_failure(cls, count: int, base_dt: datetime) -> List[Dict[str, Any]]:
        records = []
        devices = [
            ("finance-laptop-07", "endpoint", "Finance-4F", "wlan0"),
            ("sales-tablet-12", "endpoint", "Lobby", "wlan0"),
        ]
        for t in range(count):
            ts = base_dt - timedelta(seconds=(count - t) * 10)
            exhausted = t >= 2
            for dev_id, dev_type, loc, if_name in devices:
                records.append({
                    "device_id": dev_id,
                    "device_type": dev_type,
                    "timestamp": ts,
                    "location": loc,
                    "interface_name": if_name,
                    "latency_ms": 999.0 if exhausted else 14.0,
                    "jitter_ms": 0.0 if exhausted else 1.5,
                    "packet_loss_percent": 100.0 if exhausted else 0.0,
                    "throughput_mbps": 0.0 if exhausted else 60.0,
                    "bandwidth_utilization_percent": 0.0 if exhausted else 12.0,
                    "cpu_utilization_percent": 15.0,
                    "memory_utilization_percent": 32.0,
                    "device_status": DeviceStatus.DEGRADED.value if exhausted else DeviceStatus.ACTIVE.value,
                    "interface_errors": 0,
                    "queue_drops": 0,
                    "wifi_signal_dbm": -54.0,  # Wi-Fi RF link is strong
                    "dns_status": DNSStatus.TIMEOUT.value if exhausted else DNSStatus.SUCCESS.value,
                    "dhcp_status": DHCPStatus.EXHAUSTED.value if exhausted else DHCPStatus.BOUND.value,
                    "connectivity_status": ConnectivityStatus.DISCONNECTED.value if exhausted else ConnectivityStatus.CONNECTED.value,
                })
        return records

    @classmethod
    def _generate_infrastructure_overload(cls, count: int, base_dt: datetime) -> List[Dict[str, Any]]:
        records = []
        for t in range(count):
            ts = base_dt - timedelta(seconds=(count - t) * 10)
            pegged = t >= 2
            records.append({
                "device_id": "core-router-01",
                "device_type": "router",
                "timestamp": ts,
                "location": "DC-East",
                "interface_name": "TenGig0/1",
                "latency_ms": round(185.0 + (t % 3) * 18.0, 1) if pegged else 12.0,
                "jitter_ms": round(39.0 + (t % 3) * 5.0, 1) if pegged else 1.5,
                "packet_loss_percent": 6.8 if pegged else 0.0,
                "throughput_mbps": 120.0 if pegged else 800.0,
                "bandwidth_utilization_percent": 48.0,  # Link transit capacity is NOT maxed out
                "cpu_utilization_percent": round(96.5 + (t % 3) * 1.2, 1) if pegged else 32.0,  # Critical CPU
                "memory_utilization_percent": round(93.0 + (t % 2) * 1.5, 1) if pegged else 44.0,  # Critical RAM
                "device_status": DeviceStatus.DEGRADED.value if pegged else DeviceStatus.ACTIVE.value,
                "interface_errors": 0,
                "queue_drops": int(280 + t * 45) if pegged else 0,
                "wifi_signal_dbm": None,
                "dns_status": DNSStatus.SUCCESS.value,
                "dhcp_status": DHCPStatus.BOUND.value,
                "connectivity_status": ConnectivityStatus.DEGRADED.value if pegged else ConnectivityStatus.CONNECTED.value,
            })
        return records

    @classmethod
    def save_all_scenarios(cls, output_dir: Optional[Union[str, Path]] = None) -> Dict[str, Path]:
        """
        Saves all supported scenarios as both JSON and CSV files into data/scenarios/.
        """
        out_path = Path(output_dir) if output_dir else SCENARIOS_DIR
        out_path.mkdir(parents=True, exist_ok=True)
        created_files = {}

        for sc in cls.SUPPORTED_SCENARIOS:
            records = cls.generate(sc, count=12)
            dict_records = [r.model_dump(mode="json") for r in records]

            # Save JSON
            json_file = out_path / f"{sc}.json"
            with open(json_file, "w", encoding="utf-8") as f:
                json.dump(dict_records, f, indent=2)

            # Save CSV
            csv_file = out_path / f"{sc}.csv"
            df = pd.DataFrame(dict_records)
            df.to_csv(csv_file, index=False)

            created_files[f"{sc}_json"] = json_file
            created_files[f"{sc}_csv"] = csv_file

        return created_files


# Auto-generate scenario files upon module load
try:
    TelemetryGenerator.save_all_scenarios()
except Exception:
    pass
