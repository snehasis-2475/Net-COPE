from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union
import pandas as pd

from communication.models import NetworkTelemetryRecord


HEADER_MAPPING = {
    "timestamp": ["timestamp", "time", "datetime", "date_time", "ts"],
    "device_id": ["device_id", "device", "host", "hostname", "node", "node_id", "device_name"],
    "device_type": ["device_type", "type", "role", "node_type"],
    "latency_ms": ["latency_ms", "latency", "rtt", "rtt_ms", "ping_ms"],
    "jitter_ms": ["jitter_ms", "jitter", "delay_variation"],
    "packet_loss_pct": ["packet_loss_pct", "packet_loss", "loss", "loss_pct", "drop_rate"],
    "throughput_mbps": ["throughput_mbps", "throughput", "bandwidth", "tx_rate", "rx_rate"],
    "bandwidth_util_pct": ["bandwidth_util_pct", "bandwidth_util", "bw_util", "utilization_pct", "link_util", "link_utilization_pct", "link_util_pct", "link_utilization"],
    "device_availability": ["device_availability", "availability", "uptime_pct", "available"],
    "cpu_util_pct": ["cpu_util_pct", "cpu", "cpu_util", "cpu_percent", "processor_util", "cpu_utilization_pct", "cpu_utilization"],
    "memory_util_pct": ["memory_util_pct", "memory", "mem_util", "ram_util", "memory_percent"],
    "interface_status": ["interface_status", "status", "link_state", "if_state", "port_status"],
    "interface_errors": ["interface_errors", "errors", "crc_errors", "frame_errors", "rx_errors", "tx_errors"],
    "queue_drops": ["queue_drops", "drops", "buffer_drops", "tail_drops", "packet_drops"],
    "dns_resolution_status": ["dns_resolution_status", "dns_status", "dns_result", "dns_state"],
    "dns_latency_ms": ["dns_latency_ms", "dns_latency", "dns_rtt", "dns_time_ms"],
    "dhcp_status": ["dhcp_status", "dhcp_state", "dhcp_result", "lease_status"],
    "wifi_rssi_dbm": ["wifi_rssi_dbm", "wifi_rssi", "rssi", "rssi_dbm", "signal_dbm"],
    "wifi_snr_db": ["wifi_snr_db", "wifi_snr", "snr", "snr_db", "signal_noise_ratio"],
    "connectivity_status": ["connectivity_status", "connectivity", "reachability", "reachability_status"],
}


def load_telemetry_csv(
    file_source: Union[str, Path, bytes, io.StringIO, io.BytesIO],
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Parses, cleans, and normalizes CSV telemetry uploads with fuzzy header matching.
    Returns: (cleaned_dataframe, list_of_warnings_or_errors)
    """
    warnings: List[str] = []

    try:
        if isinstance(file_source, bytes):
            df = pd.read_csv(io.BytesIO(file_source))
        elif isinstance(file_source, Path):
            df = pd.read_csv(file_source)
        elif isinstance(file_source, str):
            if "\n" in file_source or "," in file_source:
                df = pd.read_csv(io.StringIO(file_source))
            else:
                df = pd.read_csv(file_source)
        else:
            df = pd.read_csv(file_source)
    except Exception as exc:
        return pd.DataFrame(), [f"Failed to read CSV: {str(exc)}"]

    if df.empty:
        return pd.DataFrame(), ["CSV file contains no records."]

    # Normalize column names: strip whitespace, lowercase, replace spaces with underscores
    original_cols = list(df.columns)
    col_mapping = {}
    normalized_cols = {col.strip().lower().replace(" ", "_"): col for col in original_cols}

    for standard_field, aliases in HEADER_MAPPING.items():
        for alias in aliases:
            if alias in normalized_cols:
                col_mapping[normalized_cols[alias]] = standard_field
                break

    renamed_df = df.rename(columns=col_mapping)

    # Check for mandatory device_id
    if "device_id" not in renamed_df.columns:
        # Check if first column has strings like devices or fallback
        if len(renamed_df.columns) > 0 and renamed_df.iloc[:, 0].dtype == "object":
            first_col = renamed_df.columns[0]
            renamed_df = renamed_df.rename(columns={first_col: "device_id"})
            warnings.append(f"No explicit 'device_id' column found; mapped '{first_col}' as device_id.")
        else:
            return pd.DataFrame(), ["Mandatory 'device_id' column is missing from CSV."]

    # Ensure timestamp column exists
    if "timestamp" not in renamed_df.columns:
        from datetime import datetime, timezone
        renamed_df["timestamp"] = datetime.now(timezone.utc).isoformat()
        warnings.append("No explicit 'timestamp' column found; assigned UTC timestamp.")

    # Convert numeric fields where applicable
    numeric_fields = [
        "latency_ms", "jitter_ms", "packet_loss_pct", "throughput_mbps",
        "bandwidth_util_pct", "device_availability", "cpu_util_pct",
        "memory_util_pct", "interface_errors", "queue_drops",
        "dns_latency_ms", "wifi_rssi_dbm", "wifi_snr_db"
    ]

    for field in numeric_fields:
        if field in renamed_df.columns:
            renamed_df[field] = pd.to_numeric(renamed_df[field], errors="coerce")

    # Clean string fields
    string_fields = ["interface_status", "dns_resolution_status", "dhcp_status", "connectivity_status"]
    for field in string_fields:
        if field in renamed_df.columns:
            renamed_df[field] = renamed_df[field].astype(str).str.strip().str.lower()
            renamed_df[field] = renamed_df[field].replace("nan", None)

    # Sanitize NaN across all columns so missing optional metrics yield None
    renamed_df = renamed_df.where(pd.notnull(renamed_df), None)

    return renamed_df, warnings
