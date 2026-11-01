from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class Alert:
    device_id: str
    timestamp: str
    metric: str
    observed_value: Any
    threshold: Any
    breach_ratio: float
    description: str


@dataclass
class BaselineDiagnosisResult:
    episode_id: str
    total_alerts: int
    predicted_scenario: str
    predicted_root_cause: str
    dominant_metric: Optional[str] = None
    max_breach_ratio: float = 0.0
    alerts: List[Alert] = field(default_factory=list)


class NaiveThresholdBaseline:
    """
    Naive Threshold-Alarm Baseline for Network Monitoring.
    
    Standard legacy NOC architecture:
    - Independent alerts on any metric threshold breach (no correlation, no causal topology).
    - Produces alert storms during cascading or multi-symptom network faults.
    - Naive root cause diagnosis: chooses whichever metric experienced the largest relative breach ratio.
    """

    THRESHOLDS = {
        "packet_loss_pct": 5.0,        # > 5% loss
        "latency_ms": 150.0,           # > 150ms RTT
        "jitter_ms": 30.0,             # > 30ms jitter
        "bandwidth_util_pct": 85.0,    # > 85% util
        "cpu_util_pct": 85.0,          # > 85% CPU
        "memory_util_pct": 85.0,       # > 85% RAM
        "queue_drops": 50,             # > 50 drops
        "interface_errors": 20,        # > 20 CRC errors
        "dns_latency_ms": 1000.0,      # > 1000ms lookup
        "wifi_rssi_dbm": -78.0,        # < -78 dBm
        "wifi_snr_db": 15.0,           # < 15 dB
    }

    METRIC_SCENARIO_MAP = {
        "dns_resolution_status": ("dns_failure", "DNS Resolver Outage or Misconfiguration"),
        "dns_latency_ms": ("dns_failure", "DNS Resolver Outage or Misconfiguration"),
        "dhcp_status": ("dhcp_failure", "DHCP Service Failure / Scope Exhaustion"),
        "interface_status": ("interface_failure", "Physical Interface / Cable Failure"),
        "interface_errors": ("interface_failure", "Physical Interface / Cable Failure"),
        "wifi_rssi_dbm": ("weak_wifi", "Wireless RF Attenuation / Weak Wi-Fi Coverage"),
        "wifi_snr_db": ("weak_wifi", "Wireless RF Attenuation / Weak Wi-Fi Coverage"),
        "cpu_util_pct": ("infrastructure_overload", "Device Hardware / Compute Resource Overload"),
        "memory_util_pct": ("infrastructure_overload", "Device Hardware / Compute Resource Overload"),
        "bandwidth_util_pct": ("congestion", "Network Bandwidth Congestion & Bufferbloat"),
        "latency_ms": ("congestion", "Network Bandwidth Congestion & Bufferbloat"),
        "jitter_ms": ("congestion", "Network Bandwidth Congestion & Bufferbloat"),
        "packet_loss_pct": ("congestion", "Network Bandwidth Congestion & Bufferbloat"),
        "queue_drops": ("congestion", "Network Bandwidth Congestion & Bufferbloat"),
    }

    def diagnose_episode(self, episode_records: List[Dict[str, Any]], episode_id: str = "") -> BaselineDiagnosisResult:
        """
        Diagnoses an episode by scanning every record, collecting all threshold violations,
        and picking the metric with the largest relative breach ratio.
        """
        if not episode_records:
            return BaselineDiagnosisResult(
                episode_id=episode_id,
                total_alerts=0,
                predicted_scenario="invalid_telemetry",
                predicted_root_cause="Invalid or Empty Telemetry",
            )

        alerts: List[Alert] = []
        max_ratio_by_metric: Dict[str, float] = {}

        for rec in episode_records:
            if not isinstance(rec, dict):
                continue

            dev = str(rec.get("device_id", "unknown"))
            ts = str(rec.get("timestamp", ""))

            # 1. Numeric metric thresholds
            for metric, thresh in self.THRESHOLDS.items():
                val = rec.get(metric)
                if val is None or not isinstance(val, (int, float)):
                    continue

                breached = False
                ratio = 0.0

                if metric == "wifi_rssi_dbm":
                    if val < thresh:  # RSSI worse than -78 dBm
                        breached = True
                        ratio = abs(val) / abs(thresh)
                elif metric == "wifi_snr_db":
                    if val < thresh:  # SNR lower than 15 dB
                        breached = True
                        ratio = thresh / max(1.0, val)
                else:
                    if val > thresh:
                        breached = True
                        ratio = val / max(1.0, thresh)

                if breached:
                    desc = f"Threshold breached: {metric} = {val} (threshold: {thresh})"
                    alerts.append(
                        Alert(
                            device_id=dev,
                            timestamp=ts,
                            metric=metric,
                            observed_value=val,
                            threshold=thresh,
                            breach_ratio=round(ratio, 2),
                            description=desc,
                        )
                    )
                    max_ratio_by_metric[metric] = max(max_ratio_by_metric.get(metric, 0.0), ratio)

            # 2. Discrete status metrics
            dns_status = str(rec.get("dns_resolution_status", "")).lower()
            if dns_status in ["timeout", "servfail", "refused"]:
                metric = "dns_resolution_status"
                ratio = 3.0
                alerts.append(
                    Alert(
                        device_id=dev,
                        timestamp=ts,
                        metric=metric,
                        observed_value=dns_status,
                        threshold="success",
                        breach_ratio=ratio,
                        description=f"DNS resolution failure: {dns_status}",
                    )
                )
                max_ratio_by_metric[metric] = max(max_ratio_by_metric.get(metric, 0.0), ratio)

            dhcp_status = str(rec.get("dhcp_status", "")).lower()
            if dhcp_status in ["exhausted", "failed", "timeout"]:
                metric = "dhcp_status"
                ratio = 3.5
                alerts.append(
                    Alert(
                        device_id=dev,
                        timestamp=ts,
                        metric=metric,
                        observed_value=dhcp_status,
                        threshold="bound",
                        breach_ratio=ratio,
                        description=f"DHCP service failure: {dhcp_status}",
                    )
                )
                max_ratio_by_metric[metric] = max(max_ratio_by_metric.get(metric, 0.0), ratio)

            if_status = str(rec.get("interface_status", "")).lower()
            if if_status in ["down", "flapping"]:
                metric = "interface_status"
                ratio = 4.0
                alerts.append(
                    Alert(
                        device_id=dev,
                        timestamp=ts,
                        metric=metric,
                        observed_value=if_status,
                        threshold="up",
                        breach_ratio=ratio,
                        description=f"Physical interface status failure: {if_status}",
                    )
                )
                max_ratio_by_metric[metric] = max(max_ratio_by_metric.get(metric, 0.0), ratio)

        if not alerts:
            return BaselineDiagnosisResult(
                episode_id=episode_id,
                total_alerts=0,
                predicted_scenario="normal",
                predicted_root_cause="Nominal Network Operation",
                dominant_metric=None,
                max_breach_ratio=0.0,
                alerts=[],
            )

        # Naive diagnosis: select the metric that experienced the largest breach ratio
        dominant_metric = max(max_ratio_by_metric.items(), key=lambda item: item[1])[0]
        max_ratio = max_ratio_by_metric[dominant_metric]
        predicted_scenario, predicted_rc = self.METRIC_SCENARIO_MAP.get(
            dominant_metric,
            ("congestion", "Network Bandwidth Congestion & Bufferbloat"),
        )

        return BaselineDiagnosisResult(
            episode_id=episode_id,
            total_alerts=len(alerts),
            predicted_scenario=predicted_scenario,
            predicted_root_cause=predicted_rc,
            dominant_metric=dominant_metric,
            max_breach_ratio=round(max_ratio, 2),
            alerts=alerts,
        )

