from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import random
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
HARD_GENERATED_DIR = DATA_DIR / "generated_hard"
HARD_GENERATED_DIR.mkdir(parents=True, exist_ok=True)


class HardTelemetryDatasetGenerator:
    """
    Deterministic Hard Telemetry Dataset Generator for NetCoop AI.
    
    Generates realistic, challenging network telemetry episodes with:
    - Fixed deterministic seed (default seed=7)
    - 2x Gaussian noise on all metric baselines
    - 10-30% randomly missing metric fields per record
    - Overlapping primary and secondary faults
    - Borderline threshold breaches (metrics near decision boundaries)
    - 10% corrupted / malformed telemetry records to test pipeline isolation
    """

    CORE_SCENARIOS = [
        "normal",
        "congestion",
        "weak_wifi",
        "interface_failure",
        "dns_failure",
        "dhcp_failure",
        "infrastructure_overload",
        "invalid_telemetry",
    ]

    SCENARIO_CLASSES = CORE_SCENARIOS + ["silent_drift"]

    EXPECTED_ROOT_CAUSES = {
        "normal": "Nominal Network Operation",
        "congestion": "Network Bandwidth Congestion & Bufferbloat",
        "weak_wifi": "Wireless RF Attenuation / Weak Wi-Fi Coverage",
        "interface_failure": "Physical Interface / Cable Failure",
        "dns_failure": "DNS Resolver Outage or Misconfiguration",
        "dhcp_failure": "DHCP Service Failure / Scope Exhaustion",
        "infrastructure_overload": "Device Hardware / Compute Resource Overload",
        "invalid_telemetry": "Invalid or Empty Telemetry",
        "silent_drift": "Silent Performance Degradation (Rolling Baseline Drift)",
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
        "silent_drift": "warning",
    }

    # Secondary fault mappings for overlapping fault injection
    SECONDARY_FAULTS = {
        "congestion": "weak_wifi",
        "weak_wifi": "infrastructure_overload",
        "interface_failure": "congestion",
        "dns_failure": "infrastructure_overload",
        "dhcp_failure": "dns_failure",
        "infrastructure_overload": "congestion",
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

    OPTIONAL_METRICS = [
        "jitter_ms",
        "throughput_mbps",
        "bandwidth_util_pct",
        "memory_util_pct",
        "queue_drops",
        "interface_errors",
        "dns_latency_ms",
        "wifi_snr_db",
    ]

    def __init__(self, seed: int = 7):
        self.seed = seed
        self.rng = random.Random(seed)

    def generate_dataset(
        self,
        episodes_per_scenario: int = 8,
        base_time: Optional[datetime] = None,
        scenarios: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
        """
        Generates at least 60 challenging diagnostic episodes (default 8 * 8 = 64 episodes).
        Returns:
            - telemetry_records: List of all generated telemetry records
            - ground_truth_labels: Ground truth labels including primary & secondary faults
            - metadata: Dataset metadata detailing noise levels, missing rates, and modifiers
        """
        self.rng = random.Random(self.seed)
        base_time = base_time or datetime(2026, 11, 1, 0, 0, 0, tzinfo=timezone.utc)

        all_telemetry: List[Dict[str, Any]] = []
        ground_truth: Dict[str, Any] = {}
        split_assignments: Dict[str, str] = {}

        ep_counter = 0

        target_scenarios = scenarios or self.CORE_SCENARIOS
        for scenario in target_scenarios:
            for sc_idx in range(episodes_per_scenario):
                ep_counter += 1
                ep_id = f"EP-HARD-{scenario.upper()}-{sc_idx + 1:03d}"

                # Assign splits: 50% dev, 25% val, 25% test
                dev_cutoff = max(1, int(episodes_per_scenario * 0.5))
                val_cutoff = max(dev_cutoff + 1, int(episodes_per_scenario * 0.75))
                if sc_idx < dev_cutoff:
                    split = "dev"
                elif sc_idx < val_cutoff:
                    split = "val"
                else:
                    split = "test"

                split_assignments[ep_id] = split

                # Determine if borderline severity should be injected (33% of episodes)
                is_borderline = (sc_idx % 3 == 0) and scenario not in ["normal", "invalid_telemetry"]

                # Determine secondary fault for overlapping symptoms
                secondary_fault = self.SECONDARY_FAULTS.get(scenario) if scenario not in ["normal", "invalid_telemetry"] else None

                # Generate episode telemetry with hard modifiers
                records, affected_devs, fault_start, fault_end = self._generate_hard_episode(
                    scenario=scenario,
                    secondary_fault=secondary_fault,
                    episode_id=ep_id,
                    episode_index=sc_idx,
                    base_time=base_time + timedelta(minutes=ep_counter * 12),
                    is_borderline=is_borderline,
                )

                all_telemetry.extend(records)

                # Store ground truth metadata (without leaking to agents)
                ground_truth[ep_id] = {
                    "episode_id": ep_id,
                    "split": split,
                    "scenario_name": scenario,
                    "ground_truth_root_cause": self.EXPECTED_ROOT_CAUSES[scenario],
                    "expected_severity": self.EXPECTED_SEVERITIES[scenario],
                    "secondary_fault": secondary_fault,
                    "is_borderline": is_borderline,
                    "affected_devices": affected_devs,
                    "fault_start_timestamp": fault_start,
                    "fault_end_timestamp": fault_end,
                    "record_count": len(records),
                    "is_fault": scenario != "normal",
                    "is_robustness_test": scenario == "invalid_telemetry",
                }

        metadata = {
            "dataset_version": "2.0.0-hard",
            "generation_timestamp": datetime.now(timezone.utc).isoformat(),
            "random_seed": self.seed,
            "total_records": len(all_telemetry),
            "total_episodes": len(ground_truth),
            "episodes_per_scenario": episodes_per_scenario,
            "scenario_classes": self.SCENARIO_CLASSES,
            "difficulty_modifiers": {
                "gaussian_noise_factor": "2x baseline variance",
                "missing_metrics_range": "10% to 30% per record",
                "overlapping_faults": True,
                "borderline_severity_rate": "33% of fault episodes",
                "corrupted_records_rate": "10% of total records",
            },
        }

        return all_telemetry, ground_truth, metadata

    def generate_episodes(
        self,
        episodes_per_scenario: int = 1,
        base_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Generates hard diagnostic episodes grouped by episode_id."""
        all_records, ground_truth, metadata = self.generate_dataset(
            episodes_per_scenario=episodes_per_scenario,
            base_time=base_time,
        )
        ep_dict: Dict[str, List[Dict[str, Any]]] = {}
        for r in all_records:
            ep_id = r.get("episode_id")
            if ep_id:
                ep_dict.setdefault(ep_id, []).append(r)

        episodes: List[Dict[str, Any]] = []
        for ep_id, records in ep_dict.items():
            gt = ground_truth.get(ep_id, {})
            sc = gt.get("scenario_name") or gt.get("scenario")
            episodes.append({
                "episode_id": ep_id,
                "scenario": sc,
                "scenario_name": sc,
                "records": records,
                "ground_truth": gt,
            })
        return episodes

    def save_dataset(
        self,
        output_dir: Optional[Path] = None,
        episodes_per_scenario: int = 8,
    ) -> Tuple[Path, Path, Path, Path]:
        """Saves hard dataset JSON, CSV, ground truth labels, and metadata."""
        out_dir = output_dir or HARD_GENERATED_DIR
        out_dir.mkdir(parents=True, exist_ok=True)

        telemetry, ground_truth, metadata = self.generate_dataset(episodes_per_scenario=episodes_per_scenario)

        json_path = out_dir / "telemetry_dataset_hard.json"
        csv_path = out_dir / "telemetry_dataset_hard.csv"
        labels_path = out_dir / "ground_truth_labels_hard.json"
        meta_path = out_dir / "dataset_metadata_hard.json"

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(telemetry, f, indent=2)

        df = pd.DataFrame(telemetry)
        df.to_csv(csv_path, index=False)

        with open(labels_path, "w", encoding="utf-8") as f:
            json.dump(ground_truth, f, indent=2)

        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        return json_path, csv_path, labels_path, meta_path

    def _select_devices_for_scenario(self, scenario: str, episode_index: int) -> List[Tuple[str, str, str, str]]:
        routers = [d for d in self.DEVICES if d[1] == "router"]
        switches = [d for d in self.DEVICES if d[1] == "switch"]
        aps = [d for d in self.DEVICES if d[1] == "ap"]
        client_endpoints = [d for d in self.DEVICES if d[0] in ["workstation-04", "laptop-sales-02"]]
        all_endpoints = [d for d in self.DEVICES if d[1] in ["endpoint", "server"]]

        r = routers[episode_index % len(routers)]
        s = switches[episode_index % len(switches)]
        ap = aps[episode_index % len(aps)]
        ep = all_endpoints[episode_index % len(all_endpoints)]

        if scenario == "weak_wifi":
            return [r, s, ap, self.DEVICES[7]]
        elif scenario == "dhcp_failure":
            dhcp_client = client_endpoints[episode_index % len(client_endpoints)]
            return [r, s, dhcp_client]
        elif scenario in ["congestion", "interface_failure", "dns_failure", "infrastructure_overload"]:
            return [r, s, ep]
        else:
            return [r, s, ap, ep]

    def _generate_silent_drift_episode(
        self,
        episode_id: str,
        episode_index: int,
        base_time: datetime,
    ) -> Tuple[List[Dict[str, Any]], List[str], Optional[str], Optional[str]]:
        """
        Generates a silent_drift episode where RTT drifts +15% to +20% over time,
        never crossing the 150ms static SLA threshold. Rules alone report NOMINAL,
        but BaselineDetector catches the statistical drift (yielding DEGRADED/PROVISIONAL).
        """
        from datetime import timedelta
        timesteps = 20
        devices = [
            ("core-router-01", "ROUTER", "datacenter-rack-1", "eth0"),
            ("edge-switch-01", "SWITCH", "datacenter-rack-2", "ge-0/0/1"),
            ("srv-db-01", "SERVER", "datacenter-rack-1", "eth0"),
            ("workstation-01", "WORKSTATION", "office-floor-2", "eth0"),
        ]
        records: List[Dict[str, Any]] = []
        affected_devices = ["core-router-01", "edge-switch-01"]

        for step in range(timesteps):
            ts = (base_time + timedelta(seconds=step * 10)).isoformat()
            is_drift = step >= 10
            drift_factor = 1.0 + (0.02 * (step - 9)) if is_drift else 1.0

            for dev_id, dev_type, loc, iface in devices:
                is_affected = dev_id in affected_devices
                base_rtt = 24.0 if is_affected else 18.0
                rtt_val = base_rtt * (drift_factor if is_affected else 1.0) + self.rng.gauss(0, 0.2)
                rtt_val = max(10.0, min(140.0, rtt_val))

                rec = {
                    "device_id": dev_id,
                    "timestamp": ts,
                    "device_role": dev_type,
                    "interface_status": "UP",
                    "packet_loss_pct": max(0.0, round(self.rng.gauss(0.05, 0.02), 2)),
                    "latency_ms": round(rtt_val, 2),
                    "rtt_ms": round(rtt_val, 2),
                    "jitter_ms": max(0.5, round(self.rng.gauss(2.0, 0.2), 2)),
                    "bandwidth_util_pct": max(10.0, round(self.rng.gauss(30.0, 2.0), 1)),
                    "cpu_utilization_pct": max(10.0, round(self.rng.gauss(25.0, 2.0), 1)),
                    "memory_utilization_pct": max(15.0, round(self.rng.gauss(35.0, 2.0), 1)),
                    "queue_drops": 0,
                    "error_count": 0,
                    "dns_status": "OK",
                    "dns_latency_ms": max(5.0, round(self.rng.gauss(12.0, 1.0), 1)),
                    "dns_failure_rate_pct": 0.0,
                    "dhcp_status": "BOUND",
                    "dhcp_response_time_ms": max(5.0, round(self.rng.gauss(15.0, 1.0), 1)),
                    "dhcp_failure_rate_pct": 0.0,
                    "episode_id": episode_id,
                }
                records.append(rec)

        root_cause = "Silent Performance Degradation (Rolling Baseline Drift)"
        desc = "RTT metric drifted +15% above rolling baseline without crossing static 150ms SLA thresholds."
        return records, affected_devices, root_cause, desc

    def _generate_hard_episode(
        self,
        scenario: str,
        secondary_fault: Optional[str],
        episode_id: str,
        episode_index: int,
        base_time: datetime,
        is_borderline: bool,
    ) -> Tuple[List[Dict[str, Any]], List[str], Optional[str], Optional[str]]:
        if scenario == "invalid_telemetry":
            return self._generate_invalid_episode(episode_id, base_time)
        if scenario == "silent_drift":
            return self._generate_silent_drift_episode(episode_id, episode_index, base_time)

        devices = self._select_devices_for_scenario(scenario, episode_index)
        timesteps = 12 + (episode_index % 4)
        records: List[Dict[str, Any]] = []

        is_gradual = (episode_index % 2 == 1)
        fault_onset_step = 5 if is_gradual else 2

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
                # 10% chance per record to inject malformed / corrupt data
                is_corrupted = (self.rng.random() < 0.10)

                rec = self._generate_hard_device_record(
                    scenario=scenario,
                    secondary_fault=secondary_fault,
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
                    is_borderline=is_borderline,
                    is_corrupted=is_corrupted,
                    episode_id=episode_id,
                )

                if fault_active and self._is_device_affected(scenario, dev_type):
                    if dev_id not in affected_devices:
                        affected_devices.append(dev_id)

                records.append(rec)

        if not affected_devices and scenario != "normal":
            affected_devices.append(devices[0][0])

        return records, affected_devices, fault_start_ts, fault_end_ts

    def _is_device_affected(self, scenario: str, dev_type: str) -> bool:
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

    def _generate_hard_device_record(
        self,
        scenario: str,
        secondary_fault: Optional[str],
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
        is_borderline: bool,
        is_corrupted: bool,
        episode_id: str,
    ) -> Dict[str, Any]:
        # 1. 2x Gaussian noise on all baselines (safely bounded to avoid artificial false alarms on healthy baselines)
        lat = max(2.0, min(40.0, round(self.rng.gauss(14.0, 4.0), 1)))  # 2x noise: std 4.0 vs 2.0
        jit = max(0.5, min(12.0, round(self.rng.gauss(2.0, 1.2), 1)))   # 2x noise: std 1.2 vs 0.6
        loss = 0.0
        tput = max(100.0, round(self.rng.gauss(550.0, 70.0), 1)) if dev_type in ["router", "switch"] else 95.0
        bw = max(5.0, min(60.0, round(self.rng.gauss(35.0, 10.0), 1)))  # 2x noise: std 10.0 vs 5.0
        cpu = max(10.0, min(58.0, round(self.rng.gauss(28.0, 9.0), 1))) # 2x noise: std 9.0 vs 4.5
        mem = max(20.0, min(62.0, round(self.rng.gauss(42.0, 6.0), 1)))
        if_status = "up"
        if_errors = 0
        q_drops = 0
        dns_status = "success"
        dns_lat = max(4.0, min(45.0, round(self.rng.gauss(10.0, 3.6), 1)))
        dhcp_status = "bound"
        wifi_rssi = max(-57.0, min(-40.0, round(self.rng.gauss(-48.0, 3.5), 1))) if dev_type in ["ap", "endpoint"] else None
        wifi_snr = max(22.0, min(45.0, round(self.rng.gauss(34.0, 4.0), 1))) if dev_type in ["ap", "endpoint"] else None
        conn_status = "connected"

        # 2. Primary Fault Injection
        if fault_active:
            progress = (step - fault_onset_step) / max(1, timesteps - fault_onset_step) if is_gradual else 1.0

            if scenario == "congestion":
                if is_borderline:
                    # Borderline: loss ~ 4.8 - 5.5% (threshold is 5.0%), latency ~ 140 - 160ms (threshold is 150ms)
                    lat = round(135.0 + 25.0 * progress + self.rng.uniform(-3.0, 3.0), 1)
                    loss = round(min(6.0, 3.5 + 2.0 * progress + self.rng.uniform(-0.3, 0.3)), 1)
                    bw = round(min(88.0, 78.0 + 9.0 * progress), 1)
                    q_drops = int(35 + 40 * progress)
                else:
                    if dev_type in ["router", "switch"]:
                        bw = round(min(98.5, 75.0 + 23.5 * progress + self.rng.uniform(-2.0, 2.0)), 1)
                        q_drops = int(80 + 350 * progress + self.rng.randint(0, 50))
                    lat = round(45.0 + 160.0 * progress + self.rng.uniform(-5.0, 20.0), 1)
                    jit = round(8.0 + 38.0 * progress + self.rng.uniform(-2.0, 8.0), 1)
                    loss = round(min(12.0, 1.5 + 4.5 * progress + self.rng.uniform(0.0, 1.5)), 1)
                conn_status = "degraded"

            elif scenario == "weak_wifi":
                if dev_type in ["ap", "endpoint"]:
                    if is_borderline:
                        # Borderline: RSSI ~ -76 to -79 dBm (threshold is -78 dBm), SNR ~ 14 to 17 dB
                        wifi_rssi = round(-74.0 - 5.0 * progress + self.rng.uniform(-1.0, 1.0), 1)
                        wifi_snr = round(18.0 - 4.0 * progress + self.rng.uniform(-1.0, 1.0), 1)
                        loss = round(min(7.0, 2.0 + 3.0 * progress), 1)
                    else:
                        wifi_rssi = round(min(-82.0, -68.0 - 18.0 * progress + self.rng.uniform(-3.0, 2.0)), 1)
                        wifi_snr = round(max(5.0, 20.0 - 13.0 * progress + self.rng.uniform(-2.0, 1.0)), 1)
                        loss = round(min(15.0, 2.0 + 6.0 * progress), 1)
                        lat = round(35.0 + 85.0 * progress, 1)
                    conn_status = "degraded"

            elif scenario == "interface_failure":
                if dev_type in ["switch", "router"] and (step >= fault_onset_step + 1):
                    if is_borderline:
                        # Intermittent framing errors without hard line down
                        if_errors = int(18 + 15 * progress + self.rng.randint(0, 8))
                        loss = round(min(8.0, 2.0 + 4.0 * progress), 1)
                        if_status = "up"
                        conn_status = "degraded"
                    else:
                        if_status = "down" if (step % 2 == 0) else "up"
                        if_errors = int(45 + 180 * progress + self.rng.randint(5, 30))
                        loss = round(min(35.0, 8.0 + 20.0 * progress), 1)
                        tput = round(max(0.0, 450.0 * (1.0 - progress)), 1)
                        conn_status = "disconnected" if if_status == "down" else "degraded"

            elif scenario == "dns_failure":
                if is_borderline:
                    # DNS latency high ~800-1100ms with only 1 timeout
                    dns_lat = round(650.0 + 400.0 * progress, 1)
                    dns_status = "timeout" if (step == timesteps - 1) else "success"
                else:
                    dns_status = "timeout" if step % 2 == 0 else "servfail"
                    dns_lat = round(250.0 + 350.0 * progress, 1)
                conn_status = "degraded"

            elif scenario == "dhcp_failure":
                if dev_type in ["endpoint", "ap"]:
                    if is_borderline:
                        dhcp_status = "exhausted" if (step % 3 == 0) else "bound"
                    else:
                        dhcp_status = "exhausted" if step % 2 == 0 else "failed"
                    conn_status = "disconnected" if dhcp_status != "bound" else "connected"

            elif scenario == "infrastructure_overload":
                if dev_type == "router":
                    if is_borderline:
                        # CPU ~ 82 - 86% (threshold is 85%)
                        cpu = round(min(88.0, 80.0 + 6.0 * progress + self.rng.uniform(-1.0, 1.0)), 1)
                        mem = round(min(85.0, 78.0 + 6.0 * progress), 1)
                        q_drops = int(40 + 30 * progress)
                    else:
                        cpu = round(min(99.0, 85.0 + 13.0 * progress + self.rng.uniform(0.0, 1.5)), 1)
                        mem = round(min(97.0, 86.0 + 10.0 * progress + self.rng.uniform(0.0, 1.0)), 1)
                        q_drops = int(120 + 380 * progress)
                    lat = round(50.0 + 140.0 * progress, 1)
                    jit = round(10.0 + 35.0 * progress, 1)
                    conn_status = "degraded"

            # 3. Secondary Overlapping Fault Injection (Subtle, non-dominant)
            if secondary_fault:
                if secondary_fault == "infrastructure_overload" and dev_type == "router":
                    cpu = max(cpu, round(78.0 + 8.0 * self.rng.random(), 1))
                elif secondary_fault == "weak_wifi" and dev_type in ["ap", "endpoint"]:
                    wifi_rssi = min(wifi_rssi or -50.0, round(-68.0 - 4.0 * self.rng.random(), 1))
                elif secondary_fault == "congestion":
                    lat = max(lat, round(85.0 + 30.0 * self.rng.random(), 1))
                    bw = max(bw, round(76.0 + 6.0 * self.rng.random(), 1))
                elif secondary_fault == "dns_failure":
                    dns_lat = max(dns_lat, round(350.0 + 150.0 * self.rng.random(), 1))

        # 4. 10% Corrupted / Malformed Record Injection
        if is_corrupted:
            corruption_type = self.rng.choice(["negative_metric", "type_error", "out_of_bounds", "corrupt_timestamp"])
            if corruption_type == "negative_metric":
                lat = -50.0
            elif corruption_type == "type_error":
                cpu = "NOT_A_FLOAT"  # type: ignore
            elif corruption_type == "out_of_bounds":
                bw = 350.0  # percentage > 100
            elif corruption_type == "corrupt_timestamp":
                timestamp = "INVALID_TIMESTAMP_STRING"

        rec: Dict[str, Any] = {
            "timestamp": timestamp,
            "device_id": dev_id,
            "device_type": dev_type,
            "interface_name": interface,
            "location": location,
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
            "connection_status": conn_status,
            "episode_id": episode_id,
        }

        # 5. 10-30% Randomly Missing Metrics per Record
        missing_rate = self.rng.uniform(0.10, 0.30)
        for opt_key in self.OPTIONAL_METRICS:
            if self.rng.random() < missing_rate:
                rec[opt_key] = None

        return rec

    def _generate_invalid_episode(
        self,
        episode_id: str,
        base_time: datetime,
    ) -> Tuple[List[Dict[str, Any]], List[str], Optional[str], Optional[str]]:
        records = []
        for step in range(8):
            ts = (base_time + timedelta(seconds=step * 10)).isoformat()
            records.append({
                "timestamp": ts,
                "device_id": f"device-{step}",
                "cpu_util_pct": "CORRUPT_STRING_VAL",
                "latency_ms": -999.0,
                "bandwidth_util_pct": 500.0,
                "packet_loss_pct": -10.0,
                "episode_id": episode_id,
            })
        return records, ["unknown"], ts, ts

