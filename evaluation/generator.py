from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from communication.telemetry_schema import TelemetryRecord

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
GENERATED_DIR = DATA_DIR / "generated"
GENERATED_DIR.mkdir(parents=True, exist_ok=True)


class TelemetryDatasetGenerator:
    """
    Reproducible Synthetic Network Telemetry Dataset Generator for NetCoop AI.
    Generates balanced diagnostic episodes across 8 scenario classes with realistic
    variations, temporal transitions, missing optional metrics, and multi-device topology.
    """

    SCENARIO_CLASSES = [
        "normal",
        "congestion",
        "weak_wifi",
        "interface_failure",
        "dns_failure",
        "dhcp_failure",
        "infrastructure_overload",
        "invalid_telemetry",
    ]

    EXPECTED_ROOT_CAUSES = {
        "normal": "Nominal Network Operation",
        "congestion": "Network Bandwidth Congestion & Bufferbloat",
        "weak_wifi": "Wireless RF Attenuation / Weak Wi-Fi Coverage",
        "interface_failure": "Physical Interface / Cable Failure",
        "dns_failure": "DNS Resolver Outage or Misconfiguration",
        "dhcp_failure": "DHCP Service Failure / Scope Exhaustion",
        "infrastructure_overload": "Device Hardware / Compute Resource Overload",
        "invalid_telemetry": "Invalid or Empty Telemetry",
    }

    EXPECTED_SEVERITIES = {
        "normal": "info",
        "congestion": "critical",
        "weak_wifi": "warning",
        "interface_failure": "critical",
        "dns_failure": "critical",
        "dhcp_failure": "critical",
        "infrastructure_overload": "critical",
        "invalid_telemetry": "critical",
    }

    DEVICES = [
        ("core-router-01", "router", "datacenter-rack1", "GigabitEthernet0/1"),
        ("core-router-02", "router", "datacenter-rack2", "GigabitEthernet0/2"),
        ("edge-switch-01", "switch", "bldg-a-floor1", "FastEthernet0/24"),
        ("edge-switch-02", "switch", "bldg-b-floor2", "FastEthernet0/12"),
        ("ap-floor1", "ap", "bldg-a-west", "wlan0"),
        ("ap-conf-room", "ap", "bldg-b-east", "wlan1"),
        ("workstation-04", "endpoint", "finance-dept", "eth0"),
        ("laptop-sales-02", "endpoint", "sales-dept", "wifi0"),
        ("server-app-01", "server", "server-farm", "eth0"),
    ]

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = random.Random(seed)

    def generate_dataset(
        self,
        episodes_per_scenario: int = 12,
        base_time: Optional[datetime] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
        """
        Generates a balanced multi-scenario dataset with ground truth labels and metadata.
        Returns:
            - telemetry_records: Clean list of telemetry records with episode_id
            - ground_truth_labels: Ground truth labels keyed by episode_id
            - metadata: Dataset metadata including statistics and split info
        """
        self.rng.seed(self.seed)
        base_time = base_time or datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)

        all_telemetry: List[Dict[str, Any]] = []
        ground_truth: Dict[str, Any] = {}
        split_assignments: Dict[str, str] = {}

        # Splits per scenario: 6 dev (50%), 3 val (25%), 3 test (25%) = 12 episodes
        # Stratified by scenario so every split has balanced representation
        ep_counter = 0

        for scenario in self.SCENARIO_CLASSES:
            for sc_idx in range(episodes_per_scenario):
                ep_counter += 1
                ep_id = f"EP-{scenario.upper()}-{sc_idx + 1:03d}"

                if episodes_per_scenario >= 4:
                    dev_cutoff = max(1, int(episodes_per_scenario * 0.5))
                    val_cutoff = max(dev_cutoff + 1, int(episodes_per_scenario * 0.75))
                    if sc_idx < dev_cutoff:
                        split = "dev"
                    elif sc_idx < val_cutoff:
                        split = "val"
                    else:
                        split = "test"
                else:
                    splits = ["dev", "val", "test"]
                    split = splits[ep_counter % len(splits)]

                split_assignments[ep_id] = split

                # Generate episode telemetry
                records, affected_devs, fault_start, fault_end = self._generate_episode(
                    scenario=scenario,
                    episode_id=ep_id,
                    episode_index=sc_idx,
                    base_time=base_time + timedelta(minutes=ep_counter * 10),
                )

                all_telemetry.extend(records)

                # Store ground truth separately (no leakage)
                ground_truth[ep_id] = {
                    "episode_id": ep_id,
                    "split": split,
                    "scenario_name": scenario,
                    "ground_truth_root_cause": self.EXPECTED_ROOT_CAUSES[scenario],
                    "expected_severity": self.EXPECTED_SEVERITIES[scenario],
                    "affected_devices": affected_devs,
                    "fault_start_timestamp": fault_start,
                    "fault_end_timestamp": fault_end,
                    "record_count": len(records),
                    "is_fault": scenario != "normal",
                    "is_robustness_test": scenario == "invalid_telemetry",
                }

        # Build comprehensive metadata
        metadata = {
            "dataset_version": "1.0.0",
            "generation_timestamp": datetime.now(timezone.utc).isoformat(),
            "random_seed": self.seed,
            "total_records": len(all_telemetry),
            "total_episodes": len(ground_truth),
            "episodes_per_scenario": episodes_per_scenario,
            "scenario_classes": self.SCENARIO_CLASSES,
            "device_count": len(self.DEVICES),
            "splits": {
                "dev": {
                    "episodes": sum(1 for ep in ground_truth.values() if ep["split"] == "dev"),
                    "records": sum(ep["record_count"] for ep in ground_truth.values() if ep["split"] == "dev"),
                },
                "val": {
                    "episodes": sum(1 for ep in ground_truth.values() if ep["split"] == "val"),
                    "records": sum(ep["record_count"] for ep in ground_truth.values() if ep["split"] == "val"),
                },
                "test": {
                    "episodes": sum(1 for ep in ground_truth.values() if ep["split"] == "test"),
                    "records": sum(ep["record_count"] for ep in ground_truth.values() if ep["split"] == "test"),
                },
            },
            "scenario_distribution": {
                sc: sum(1 for ep in ground_truth.values() if ep["scenario_name"] == sc)
                for sc in self.SCENARIO_CLASSES
            },
            "feature_descriptions": {
                "device_id": "Unique identifier of the reporting network device",
                "device_type": "Device role or category (router, switch, ap, endpoint, server)",
                "timestamp": "ISO 8601 UTC timestamp of measurement",
                "latency_ms": "Round trip delay in milliseconds",
                "jitter_ms": "Packet delay variation in milliseconds",
                "packet_loss_pct": "Percentage of packet loss (0.0 to 100.0)",
                "throughput_mbps": "Observed throughput in Megabits per second",
                "bandwidth_util_pct": "Interface bandwidth consumption percentage",
                "cpu_util_pct": "Supervisor / CPU processor utilization percentage",
                "memory_util_pct": "Device memory utilization percentage",
                "interface_status": "Operational link state ('up' or 'down')",
                "interface_errors": "Cumulative CRC / framing / FCS error count",
                "queue_drops": "Tail drops due to buffer saturation",
                "dns_resolution_status": "DNS query status ('success', 'timeout', 'servfail')",
                "dns_latency_ms": "DNS name resolution round trip latency",
                "dhcp_status": "DHCP lease binding state ('bound', 'exhausted', 'failed')",
                "wifi_rssi_dbm": "Received Wi-Fi signal power level in dBm",
                "wifi_snr_db": "Wi-Fi Signal-to-Noise ratio in dB",
                "connectivity_status": "Overall connectivity state ('connected', 'degraded', 'disconnected')",
            },
        }

        return all_telemetry, ground_truth, metadata

    def save_dataset(
        self,
        output_dir: Optional[Path] = None,
        episodes_per_scenario: int = 12,
    ) -> Tuple[Path, Path, Path, Path]:
        """
        Generates and saves dataset files to disk:
        - telemetry_dataset.json
        - telemetry_dataset.csv
        - ground_truth_labels.json
        - dataset_metadata.json
        """
        out_dir = output_dir or GENERATED_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        telemetry, ground_truth, metadata = self.generate_dataset(episodes_per_scenario=episodes_per_scenario)

        json_path = out_dir / "telemetry_dataset.json"
        csv_path = out_dir / "telemetry_dataset.csv"
        labels_path = out_dir / "ground_truth_labels.json"
        meta_path = out_dir / "dataset_metadata.json"

        # 1. Save telemetry JSON
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(telemetry, f, indent=2)

        # 2. Save telemetry CSV
        df = pd.DataFrame(telemetry)
        df.to_csv(csv_path, index=False)

        # 3. Save ground truth labels (strictly separate)
        with open(labels_path, "w", encoding="utf-8") as f:
            json.dump(ground_truth, f, indent=2)

        # 4. Save metadata
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        return json_path, csv_path, labels_path, meta_path

    def _select_devices_for_scenario(self, scenario: str, episode_index: int) -> List[Tuple[str, str, str, str]]:
        """Selects a realistic network topology subset ensuring relevant devices are present."""
        routers = [self.DEVICES[0], self.DEVICES[1]]
        switches = [self.DEVICES[2], self.DEVICES[3]]
        aps = [self.DEVICES[4], self.DEVICES[5]]
        endpoints = [self.DEVICES[6], self.DEVICES[7], self.DEVICES[8]]

        r = routers[episode_index % len(routers)]
        s = switches[episode_index % len(switches)]
        ap = aps[episode_index % len(aps)]
        ep = endpoints[episode_index % len(endpoints)]

        if scenario == "weak_wifi":
            # Must include AP and wireless endpoint, plus upstream switch
            return [r, s, ap, self.DEVICES[7]]  # laptop-sales-02 is wifi endpoint
        elif scenario == "dhcp_failure":
            # Must include client endpoint and upstream infrastructure
            return [r, s, ep]
        elif scenario == "congestion":
            return [r, s, ep]
        elif scenario == "interface_failure":
            return [r, s, ep]
        elif scenario == "dns_failure":
            return [r, s, ep]
        elif scenario == "infrastructure_overload":
            return [r, s, ep]
        else:  # normal
            return [r, s, ap, ep]

    def _generate_episode(
        self,
        scenario: str,
        episode_id: str,
        episode_index: int,
        base_time: datetime,
    ) -> Tuple[List[Dict[str, Any]], List[str], Optional[str], Optional[str]]:
        """
        Generates realistic time-series records for an episode.
        Applies gradual onset, sudden onset, missing optional metrics, and random noise.
        """
        if scenario == "invalid_telemetry":
            return self._generate_invalid_episode(episode_id, base_time)

        # Select devices involved in this episode with realistic topology
        devices = self._select_devices_for_scenario(scenario, episode_index)

        # 12 to 16 timesteps per episode
        timesteps = 14 + (episode_index % 3)
        records: List[Dict[str, Any]] = []

        # Determine fault onset mode: gradual (starts at 40% duration) or sudden (starts at step 3)
        is_gradual = (episode_index % 2 == 1)
        fault_onset_step = 6 if is_gradual else 3

        fault_start_ts: Optional[str] = None
        fault_end_ts: Optional[str] = None
        affected_devices: List[str] = []

        for step in range(timesteps):
            ts = (base_time + timedelta(seconds=step * 10)).isoformat()
            fault_active = (step >= fault_onset_step) and (scenario != "normal")

            if fault_active and fault_start_ts is None:
                fault_start_ts = ts
            if fault_active:
                fault_end_ts = ts

            for dev_id, dev_type, loc, iface in devices:
                rec = self._generate_device_record(
                    scenario=scenario,
                    dev_id=dev_id,
                    dev_type=dev_type,
                    location=loc,
                    interface=iface,
                    timestamp=ts,
                    step=step,
                    timesteps=timesteps,
                    fault_active=fault_active,
                    fault_onset_step=fault_onset_step,
                    is_gradual=is_gradual,
                    episode_id=episode_id,
                )

                if fault_active and self._is_device_affected(scenario, dev_id, dev_type):
                    if dev_id not in affected_devices:
                        affected_devices.append(dev_id)

                records.append(rec)

        if not affected_devices and scenario != "normal":
            affected_devices.append(devices[0][0])

        return records, affected_devices, fault_start_ts, fault_end_ts

    def _is_device_affected(self, scenario: str, dev_id: str, dev_type: str) -> bool:
        if scenario == "congestion":
            return dev_type in ["router", "switch"]
        elif scenario == "weak_wifi":
            return dev_type in ["ap", "endpoint"]
        elif scenario == "interface_failure":
            return dev_type in ["switch", "router"]
        elif scenario == "dns_failure":
            return True
        elif scenario == "dhcp_failure":
            return dev_type in ["endpoint", "ap"]
        elif scenario == "infrastructure_overload":
            return dev_type == "router"
        return False

    def _generate_device_record(
        self,
        scenario: str,
        dev_id: str,
        dev_type: str,
        location: str,
        interface: str,
        timestamp: str,
        step: int,
        timesteps: int,
        fault_active: bool,
        fault_onset_step: int,
        is_gradual: bool,
        episode_id: str,
    ) -> Dict[str, Any]:
        """Synthesizes a single telemetry record with realistic variation."""
        # Baseline normal values with natural Gaussian noise
        lat = max(2.0, round(self.rng.gauss(14.0, 2.5), 1))
        jit = max(0.5, round(self.rng.gauss(2.0, 0.6), 1))
        loss = 0.0
        tput = max(100.0, round(self.rng.gauss(550.0, 40.0), 1)) if dev_type in ["router", "switch"] else 95.0
        bw = max(5.0, min(65.0, round(self.rng.gauss(35.0, 6.0), 1)))
        cpu = max(10.0, min(55.0, round(self.rng.gauss(28.0, 5.0), 1)))
        mem = max(20.0, min(60.0, round(self.rng.gauss(42.0, 3.0), 1)))
        if_status = "up"
        if_errors = 0
        q_drops = 0
        dns_status = "success"
        dns_lat = max(4.0, round(self.rng.gauss(9.0, 1.8), 1))
        dhcp_status = "bound"
        wifi_rssi = max(-65.0, round(self.rng.gauss(-52.0, 3.0), 1)) if dev_type in ["ap", "endpoint"] else None
        wifi_snr = max(25.0, round(self.rng.gauss(34.0, 2.5), 1)) if dev_type in ["ap", "endpoint"] else None
        conn_status = "connected"

        # Occasional 1-reading noisy glitch (5% chance) on healthy records
        if not fault_active and self.rng.random() < 0.05:
            jit += round(self.rng.uniform(3.0, 8.0), 1)

        # Apply Scenario Fault Injection
        if fault_active:
            progress = (step - fault_onset_step) / max(1, timesteps - fault_onset_step) if is_gradual else 1.0

            if scenario == "congestion":
                if dev_type in ["router", "switch"]:
                    bw = round(min(98.5, 75.0 + 23.5 * progress + self.rng.uniform(-1.0, 1.5)), 1)
                    q_drops = int(80 + 350 * progress + self.rng.randint(0, 40))
                lat = round(45.0 + 160.0 * progress + self.rng.uniform(0.0, 15.0), 1)
                jit = round(8.0 + 38.0 * progress + self.rng.uniform(0.0, 6.0), 1)
                loss = round(min(12.0, 1.5 + 4.5 * progress + self.rng.uniform(0.0, 1.0)), 1)
                conn_status = "degraded"

            elif scenario == "weak_wifi":
                if dev_type in ["ap", "endpoint"]:
                    wifi_rssi = round(min(-82.0, -68.0 - 18.0 * progress + self.rng.uniform(-2.0, 1.0)), 1)
                    wifi_snr = round(max(6.0, 20.0 - 12.0 * progress + self.rng.uniform(-1.0, 1.0)), 1)
                    loss = round(min(15.0, 2.0 + 6.0 * progress), 1)
                    lat = round(35.0 + 85.0 * progress, 1)
                    conn_status = "degraded"

            elif scenario == "interface_failure":
                if dev_type in ["switch", "router"] and (step >= fault_onset_step + 1):
                    if_status = "down" if (step % 2 == 0) else "up"  # Flapping
                    if_errors = int(45 + 180 * progress + self.rng.randint(5, 30))
                    loss = round(min(35.0, 8.0 + 20.0 * progress), 1)
                    tput = round(max(0.0, 450.0 * (1.0 - progress)), 1)
                    conn_status = "disconnected" if if_status == "down" else "degraded"

            elif scenario == "dns_failure":
                dns_status = "timeout" if step % 2 == 0 else "servfail"
                dns_lat = round(250.0 + 350.0 * progress, 1)
                conn_status = "degraded"

            elif scenario == "dhcp_failure":
                if dev_type in ["endpoint", "ap"]:
                    dhcp_status = "exhausted" if step % 2 == 0 else "failed"
                    conn_status = "disconnected"

            elif scenario == "infrastructure_overload":
                if dev_type == "router":
                    cpu = round(min(99.0, 85.0 + 13.0 * progress + self.rng.uniform(0.0, 1.5)), 1)
                    mem = round(min(97.0, 86.0 + 10.0 * progress + self.rng.uniform(0.0, 1.0)), 1)
                    q_drops = int(120 + 380 * progress)
                lat = round(50.0 + 150.0 * progress, 1)
                jit = round(10.0 + 35.0 * progress, 1)
                conn_status = "degraded"

        # Build clean telemetry record
        record: Dict[str, Any] = {
            "episode_id": episode_id,
            "device_id": dev_id,
            "device_type": dev_type,
            "timestamp": timestamp,
            "location": location,
            "interface_name": interface,
            "latency_ms": lat,
            "jitter_ms": jit,
            "packet_loss_pct": loss,
            "throughput_mbps": tput,
            "bandwidth_util_pct": bw,
            "cpu_util_pct": cpu,
            "memory_util_pct": mem,
            "interface_status": if_status,
            "interface_errors": if_errors,
            "queue_drops": q_drops,
            "dns_resolution_status": dns_status,
            "dns_latency_ms": dns_lat,
            "dhcp_status": dhcp_status,
            "wifi_rssi_dbm": wifi_rssi,
            "wifi_snr_db": wifi_snr,
            "connectivity_status": conn_status,
        }

        # 10% chance to omit non-essential optional metrics to test robustness
        if self.rng.random() < 0.10:
            record["location"] = None
        if self.rng.random() < 0.10:
            record["interface_name"] = None

        return record

    def _generate_invalid_episode(
        self,
        episode_id: str,
        base_time: datetime,
    ) -> Tuple[List[Dict[str, Any]], List[str], Optional[str], Optional[str]]:
        """Generates invalid telemetry records with corrupt schemas and illegal values."""
        records = [
            {
                "episode_id": episode_id,
                "timestamp": "corrupted-datetime-format",
                "device_id": "",
                "latency_ms": -450.0,
                "packet_loss_pct": 300.0,
            },
            {
                "episode_id": episode_id,
                "timestamp": None,
                "device_id": None,
                "cpu_util_pct": 250.0,
            },
            {
                "episode_id": episode_id,
                "random_noise_key": "unrecognized_malformed_json",
                "value": "null",
            },
            {
                "episode_id": episode_id,
                "device_id": "malformed-box-99",
                "timestamp": (base_time + timedelta(seconds=10)).isoformat(),
                "interface_status": "illegal_status_enum_value",
                "bandwidth_util_pct": -88.0,
            },
        ]
        return records, ["malformed-box-99"], base_time.isoformat(), (base_time + timedelta(seconds=30)).isoformat()
