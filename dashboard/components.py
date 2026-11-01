from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import pandas as pd
import requests

from communication.models import AgentStatus, Finding, Severity
from diagnosis.models import CorrectiveAction, DiagnosticReport, NetworkHealthStatus

# -----------------------------------------------------------------------------
# CANONICAL AGENT DEFINITIONS
# -----------------------------------------------------------------------------

CANONICAL_AGENTS = [
    {
        "id": "performance_agent",
        "name": "Performance Agent",
        "domain": "Latency, Jitter, Packet Loss, Bandwidth",
        "icon": "⚡",
    },
    {
        "id": "infrastructure_agent",
        "name": "Infrastructure Health Agent",
        "domain": "CPU, Memory, Interface Status, Hardware Queue",
        "icon": "🖥️",
    },
    {
        "id": "connectivity_agent",
        "name": "Connectivity Agent",
        "domain": "DNS, DHCP, Wi-Fi RF, Reachability",
        "icon": "🌐",
    },
    {
        "id": "correlation_agent",
        "name": "Fault Correlation Agent",
        "domain": "Multi-Symptom Evidence Synthesis & Conflict Resolution",
        "icon": "🧠",
    },
    {
        "id": "recommendation_agent",
        "name": "Recommendation Agent",
        "domain": "Remediation Runbooks & Corrective Actions",
        "icon": "🛠️",
    },
]

# -----------------------------------------------------------------------------
# 1. NETWORK OVERVIEW HELPERS
# -----------------------------------------------------------------------------

def get_health_badge(health: Union[str, NetworkHealthStatus]) -> Dict[str, str]:
    """
    Returns visual badge attributes for overall network health:
    NOMINAL, DEGRADED, CRITICAL, UNKNOWN.
    """
    val = health.value if isinstance(health, NetworkHealthStatus) else str(health).upper()
    if val in ("NOMINAL", "HEALTHY"):
        return {
            "label": "NOMINAL",
            "css_class": "badge-healthy",
            "color": "#10B981",
            "bg": "#064E3B",
            "icon": "🟢",
            "description": "Network operates within baseline SLAs across all domains.",
        }
    elif val == "DEGRADED":
        return {
            "label": "DEGRADED",
            "css_class": "badge-degraded",
            "color": "#F59E0B",
            "bg": "#78350F",
            "icon": "🟡",
            "description": "Network performance impaired or redundancy lost; SLA breached.",
        }
    elif val == "CRITICAL":
        return {
            "label": "CRITICAL",
            "css_class": "badge-critical",
            "color": "#EF4444",
            "bg": "#7F1D1D",
            "icon": "🔴",
            "description": "Severe network failure, service outage, or hard hardware fault.",
        }
    else:
        return {
            "label": "UNKNOWN",
            "css_class": "badge-unknown",
            "color": "#94A3B8",
            "bg": "#334155",
            "icon": "⚪",
            "description": "Telemetry insufficient, corrupt, or unobserved.",
        }


def get_fault_detection_badge(fault_detected: bool) -> Dict[str, str]:
    """Returns visual badge for binary fault detection state."""
    if fault_detected:
        return {
            "label": "FAULT DETECTED",
            "color": "#EF4444",
            "bg": "#450A0A",
            "icon": "⚠️",
            "text": "Active network anomaly or hardware impairment detected.",
        }
    return {
        "label": "NO FAULTS DETECTED",
        "color": "#10B981",
        "bg": "#022C22",
        "icon": "🛡️",
        "text": "All observed metrics comply with operational thresholds.",
    }


def get_certainty_badge(certainty: str) -> Dict[str, str]:
    """
    Returns visual badge attributes for hypothesis diagnostic certainty:
    CONFIRMED, PROVISIONAL, INDETERMINATE, NOT_APPLICABLE.
    """
    cert_upper = str(certainty).upper()
    if cert_upper == "CONFIRMED":
        return {
            "label": "CONFIRMED",
            "color": "#10B981",
            "icon": "🎯",
            "description": "Decisive multi-domain corroboration with zero contradicting evidence.",
        }
    elif cert_upper == "PROVISIONAL":
        return {
            "label": "PROVISIONAL",
            "color": "#F59E0B",
            "icon": "⏳",
            "description": "Evidence supports hypothesis but domain coverage or telemetry is partial.",
        }
    elif cert_upper == "INDETERMINATE":
        return {
            "label": "INDETERMINATE",
            "color": "#EF4444",
            "icon": "❓",
            "description": "Unresolved contradictions or telemetry insufficient to isolate root cause.",
        }
    else:
        return {
            "label": "NOT APPLICABLE",
            "color": "#38BDF8",
            "icon": "ℹ️",
            "description": "No active fault detected; diagnostic hypothesis is not applicable.",
        }


def get_confidence_display(report: Optional[DiagnosticReport]) -> Dict[str, Any]:
    """
    Returns confidence display data without fabricating a root-cause confidence
    score when network is healthy.
    """
    if not report:
        return {
            "is_applicable": False,
            "display_text": "—",
            "subtext": "Awaiting diagnosis execution",
            "value": None,
        }

    # Healthy networks do not display a fabricated root cause confidence score
    if not report.fault_detected or report.health_classification == "NOMINAL":
        return {
            "is_applicable": False,
            "display_text": "N/A",
            "subtext": "Baseline Operational State (No Fault Detected)",
            "value": None,
        }

    conf_score = report.root_cause_confidence
    if conf_score is None:
        conf_score = report.confidence_score if report.confidence_score > 0 else None

    if conf_score is not None:
        subtext = (
            report.confidence_interpretation.replace("_", " ").title()
            if report.confidence_interpretation
            else "Calibrated Heuristic Score"
        )
        return {
            "is_applicable": True,
            "display_text": f"{conf_score * 100:.1f}%",
            "subtext": subtext,
            "value": conf_score,
        }

    return {
        "is_applicable": False,
        "display_text": "INDETERMINATE",
        "subtext": "Insufficient evidence for confidence score",
        "value": None,
    }


# -----------------------------------------------------------------------------
# 2. AGENT EXECUTION SUMMARY HELPERS
# -----------------------------------------------------------------------------

def get_agent_status_grid(report: Optional[DiagnosticReport]) -> List[Dict[str, Any]]:
    """
    Builds status, duration, findings, and error info for all 5 canonical agents.
    Crucial: A failed or timed-out agent is never marked as healthy.
    """
    grid = []
    if not report:
        for a in CANONICAL_AGENTS:
            grid.append({
                "agent_id": a["id"],
                "name": a["name"],
                "domain": a["domain"],
                "icon": a["icon"],
                "status": "AWAITING_RUN",
                "status_color": "#94A3B8",
                "duration_ms": None,
                "findings_count": 0,
                "evidence_count": 0,
                "errors": [],
                "is_healthy": False,
            })
        return grid

    summary_map = report.agent_execution_summary or {}
    findings_map = report.individual_agent_findings or {}
    success_set = set(report.successful_agents or [])
    failed_set = set(report.failed_agents or [])
    timeout_set = set(report.timed_out_agents or [])

    for a in CANONICAL_AGENTS:
        aid = a["id"]
        meta_summary = summary_map.get(aid, {})
        msg = findings_map.get(aid)

        # Determine true status
        if aid in timeout_set:
            status = "TIMEOUT"
            status_color = "#F59E0B"
            is_healthy = False
        elif aid in failed_set:
            status = "FAILED"
            status_color = "#EF4444"
            is_healthy = False
        elif aid in success_set:
            status = "SUCCESS"
            status_color = "#10B981"
            is_healthy = True
        elif msg is not None:
            if msg.status == AgentStatus.SUCCESS:
                status = "SUCCESS"
                status_color = "#10B981"
                is_healthy = True
            elif msg.status == AgentStatus.TIMEOUT:
                status = "TIMEOUT"
                status_color = "#F59E0B"
                is_healthy = False
            else:
                status = "FAILED"
                status_color = "#EF4444"
                is_healthy = False
        else:
            status = "NOT_DISPATCHED"
            status_color = "#64748B"
            is_healthy = False

        # Metrics & Errors
        dur = meta_summary.get("execution_duration_ms") or meta_summary.get("duration_ms")
        if dur is None and msg and msg.metadata:
            dur = msg.metadata.get("execution_time_ms")

        f_count = meta_summary.get("finding_count", 0)
        ev_count = meta_summary.get("evidence_count", 0)
        errors = list(meta_summary.get("errors", []))

        if msg:
            if not f_count and msg.findings:
                f_count = len(msg.findings)
            if not ev_count and msg.evidence:
                ev_count = len(msg.evidence)
            if msg.errors:
                for err in msg.errors:
                    if err not in errors:
                        errors.append(err)

        grid.append({
            "agent_id": aid,
            "name": a["name"],
            "domain": a["domain"],
            "icon": a["icon"],
            "status": status,
            "status_color": status_color,
            "duration_ms": dur,
            "findings_count": f_count,
            "evidence_count": ev_count,
            "errors": errors,
            "is_healthy": is_healthy,
        })

    return grid


# -----------------------------------------------------------------------------
# 3. FINDINGS & EVIDENCE EXPLORER HELPERS
# -----------------------------------------------------------------------------

def build_findings_table(report: Optional[DiagnosticReport]) -> pd.DataFrame:
    """
    Builds a clean, structured DataFrame containing all required finding fields:
    Finding ID, Source agent, Device, Interface, Metric, Observed value,
    Threshold, Severity, Timestamp, Finding type.
    """
    if not report:
        return pd.DataFrame()

    findings_list: List[Finding] = []
    if report.validated_findings:
        findings_list.extend(report.validated_findings)

    # Corroborate with individual agent findings if validated_findings is empty
    if not findings_list and report.individual_agent_findings:
        for aid, msg in report.individual_agent_findings.items():
            if msg.findings:
                for f in msg.findings:
                    if not f.source_agent:
                        f.source_agent = aid
                    findings_list.append(f)

    if not findings_list:
        return pd.DataFrame()

    rows = []
    for f in findings_list:
        dev_str = ", ".join(f.affected_devices) if f.affected_devices else (getattr(f, "device_id", None) or "global")
        obs_val = f.observed_value
        thresh_val = f.threshold_value

        # Format values cleanly
        obs_str = f"{obs_val:.2f}" if isinstance(obs_val, float) else (str(obs_val) if obs_val is not None else "—")
        thresh_str = f"{thresh_val:.2f}" if isinstance(thresh_val, float) else (str(thresh_val) if thresh_val is not None else "—")

        # Format timestamp
        ts_str = f.timestamp.strftime("%Y-%m-%d %H:%M:%S") if isinstance(f.timestamp, datetime) else str(f.timestamp or "—")

        rows.append({
            "Finding ID": f.finding_id,
            "Source Agent": f.source_agent or "domain_agent",
            "Device": dev_str,
            "Interface": f.interface_name or "—",
            "Metric": f.metric_name or "—",
            "Observed Value": obs_str,
            "Threshold": thresh_str,
            "Severity": f.severity.value if isinstance(f.severity, Severity) else str(f.severity).upper(),
            "Timestamp": ts_str,
            "Finding Type": f.finding_type or f.title,
            "Description": f.description,
        })

    return pd.DataFrame(rows)


def build_evidence_table(report: Optional[DiagnosticReport]) -> pd.DataFrame:
    """Builds a structured DataFrame of supporting evidence items."""
    if not report or not report.supporting_evidence:
        return pd.DataFrame()

    rows = []
    for idx, ev in enumerate(report.supporting_evidence):
        unit_str = f" {ev.unit}" if ev.unit else ""
        obs_str = f"{ev.observed_value}{unit_str}" if ev.observed_value is not None else "—"
        thresh_str = f"{ev.threshold}{unit_str}" if ev.threshold is not None else "—"
        ev_id = getattr(ev, "evidence_id", None) or f"EVD-{idx+1:03d}"

        rows.append({
            "Evidence ID": ev_id,
            "Metric Name": ev.metric_name,
            "Observed Value": obs_str,
            "Normal Baseline": thresh_str,
            "Finding Type": getattr(ev, "finding_type", "ANOMALY") or "ANOMALY",
            "Device": getattr(ev, "device_id", None) or "—",
            "Interface": getattr(ev, "interface_name", None) or "—",
            "Breach Details": ev.details or "Threshold violation observed.",
        })

    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# 4. RECOMMENDATIONS & RUNBOOKS HELPERS
# -----------------------------------------------------------------------------

def categorize_action(action: CorrectiveAction) -> Dict[str, Any]:
    """
    Parses a corrective action into visual categories distinguishing:
    - READ-ONLY Diagnostic checks
    - CONFIGURATION changes
    - DISRUPTIVE actions requiring NOC approval
    """
    act_type = str(getattr(action, "action_type", "DIAGNOSTIC") or "DIAGNOSTIC").upper()
    risk_level = str(getattr(action, "execution_risk", "LOW") or "LOW").upper()
    if act_type in ("DIAGNOSTIC", "VERIFICATION", "INSPECTION"):
        category_label = "READ-ONLY DIAGNOSTIC"
        category_color = "#38BDF8"
        is_disruptive = False
    elif act_type in ("CONFIGURATION", "TRAFFIC_ENGINEERING", "RATE_LIMITING"):
        category_label = "CONFIGURATION CHANGE"
        category_color = "#F59E0B"
        is_disruptive = risk_level in ("MEDIUM", "HIGH")
    else:
        category_label = "DISRUPTIVE REMEDIATION"
        category_color = "#EF4444"
        is_disruptive = True

    # Approval requirements taken directly from report with fail-safe safety:
    # 1. Missing approval information is NEVER interpreted as pre-approved.
    # 2. Disruptive or high-risk actions always mandate NOC operator approval.
    raw_approval = getattr(action, "requires_human_approval", None)
    if raw_approval is True or is_disruptive or risk_level == "HIGH":
        needs_approval = True
    elif raw_approval is False and risk_level == "LOW" and not is_disruptive:
        needs_approval = False
    else:
        # Missing or unspecified approval information: fail-safe to requiring approval
        needs_approval = True

    p = getattr(action, "priority", 2)
    priority_badge = {
        1: ("P1 - CRITICAL / IMMEDIATE", "#EF4444"),
        2: ("P2 - HIGH / SHORT-TERM", "#F59E0B"),
        3: ("P3 - MEDIUM / PLANNED", "#38BDF8"),
        4: ("P4 - LOW / HARDENING", "#10B981"),
        5: ("P5 - ADVISORY", "#94A3B8"),
    }.get(p, (f"P{p}", "#94A3B8"))

    risk_badge = {
        "LOW": ("LOW RISK", "#10B981"),
        "MEDIUM": ("MEDIUM RISK", "#F59E0B"),
        "HIGH": ("HIGH RISK", "#EF4444"),
    }.get(risk_level, (risk_level, "#94A3B8"))

    # Evidence, prerequisites, verification, rollback
    raw_prereqs = getattr(action, "prerequisites", [])
    prereqs = list(raw_prereqs) if isinstance(raw_prereqs, (list, tuple, set)) else []
    raw_verifs = getattr(action, "verification_steps", [])
    verifs = list(raw_verifs) if isinstance(raw_verifs, (list, tuple, set)) else []
    if not verifs and getattr(action, "verification_step", ""):
        verifs = [action.verification_step]
    raw_rollbacks = getattr(action, "rollback_steps", [])
    rollbacks = list(raw_rollbacks) if isinstance(raw_rollbacks, (list, tuple, set)) else []

    return {
        "action_id": getattr(action, "action_id", "") or getattr(action, "recommendation_id", ""),
        "title": action.title,
        "description": action.description,
        "category_label": category_label,
        "category_color": category_color,
        "priority_label": priority_badge[0],
        "priority_color": priority_badge[1],
        "risk_label": risk_badge[0],
        "risk_color": risk_badge[1],
        "requires_human_approval": needs_approval,
        "is_disruptive": is_disruptive,
        "affected_devices": getattr(action, "affected_devices", []) or [],
        "supporting_evidence": getattr(action, "supporting_evidence", []) or [],
        "prerequisites": prereqs,
        "verification_steps": verifs,
        "rollback_steps": rollbacks,
        "automation_command": getattr(action, "automation_command", None),
    }


# -----------------------------------------------------------------------------
# 5. TELEMETRY VISUALIZATION HELPERS
# -----------------------------------------------------------------------------

METRIC_CONFIG = {
    "latency_ms": {"label": "Latency", "unit": "ms", "color": "#38BDF8"},
    "jitter_ms": {"label": "Jitter", "unit": "ms", "color": "#818CF8"},
    "packet_loss_pct": {"label": "Packet Loss", "unit": "%", "color": "#F87171"},
    "throughput_mbps": {"label": "Throughput", "unit": "Mbps", "color": "#34D399"},
    "bandwidth_util_pct": {"label": "Bandwidth Utilization", "unit": "%", "color": "#FB923C"},
    "cpu_util_pct": {"label": "CPU Utilization", "unit": "%", "color": "#F43F5E"},
    "memory_util_pct": {"label": "Memory Utilization", "unit": "%", "color": "#A855F7"},
    "wifi_rssi_dbm": {"label": "Wi-Fi Signal Strength (RSSI)", "unit": "dBm", "color": "#2DD4BF"},
    "queue_drops": {"label": "Queue Drops", "unit": "drops", "color": "#E11D48"},
    "interface_errors": {"label": "Interface / CRC Errors", "unit": "errors", "color": "#C084FC"},
}


def analyze_telemetry_dataset(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Analyzes telemetry dataframe to determine whether data is chronological
    time-series or single snapshot, and lists available metrics with data.
    """
    if df.empty:
        return {
            "is_empty": True,
            "mode": "empty",
            "record_count": 0,
            "device_count": 0,
            "available_metrics": [],
            "devices": [],
        }

    devices = sorted(list(df["device_id"].dropna().unique())) if "device_id" in df.columns else []

    # Check for chronological time-series: has 'timestamp' with multiple distinct values
    is_time_series = False
    if "timestamp" in df.columns:
        valid_ts = df["timestamp"].dropna()
        if len(valid_ts) > 1 and valid_ts.nunique() > 1:
            is_time_series = True

    # Find available metrics that have at least one non-null value
    available_metrics = []
    for col, cfg in METRIC_CONFIG.items():
        if col in df.columns and df[col].notna().any():
            available_metrics.append({
                "column": col,
                "label": cfg["label"],
                "unit": cfg["unit"],
                "color": cfg["color"],
                "min": float(df[col].min()),
                "max": float(df[col].max()),
                "mean": float(df[col].mean()),
            })

    return {
        "is_empty": False,
        "mode": "time_series" if is_time_series else "snapshot",
        "record_count": len(df),
        "device_count": len(devices),
        "devices": devices,
        "available_metrics": available_metrics,
    }


def prepare_telemetry_dataframe(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Normalizes telemetry dataframe for Plotly visualizations:
    - Parses timestamps and sorts chronologically if time-series.
    - Converts metric columns to numeric without zero-filling (preserves NaNs).
    - Detects whether dataset is time-series or single snapshot.
    """
    if df.empty:
        return df, analyze_telemetry_dataset(df)

    clean_df = df.copy()

    # Convert known metrics to numeric, coercing invalid values to NaN (DO NOT zero-fill)
    for col in METRIC_CONFIG.keys():
        if col in clean_df.columns:
            clean_df[col] = pd.to_numeric(clean_df[col], errors="coerce")

    # Chronological sorting on timestamp if present
    is_time_series = False
    if "timestamp" in clean_df.columns:
        clean_df["_parsed_ts"] = pd.to_datetime(clean_df["timestamp"], errors="coerce")
        valid_ts = clean_df["_parsed_ts"].dropna()
        if len(valid_ts) > 1 and valid_ts.nunique() > 1:
            clean_df = clean_df.sort_values(by="_parsed_ts", ascending=True)
            is_time_series = True

    meta = analyze_telemetry_dataset(clean_df)
    meta["mode"] = "time_series" if is_time_series else "snapshot"
    return clean_df, meta


# -----------------------------------------------------------------------------
# 6. REPORT HISTORY & API RETRIEVAL HELPERS
# -----------------------------------------------------------------------------

def list_saved_reports(reports_dir: Union[str, Path]) -> List[Dict[str, Any]]:
    """
    Retrieves and summarizes previously generated reports from disk.
    Returns structured list with report_id, diagnosis_id, timestamp, health, fault, and summary.
    Handles empty history or non-existent directories gracefully.
    """
    p = Path(reports_dir)
    if not p.exists() or not p.is_dir():
        return []

    reports = []
    for f in p.glob("*.json"):
        try:
            raw = f.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, dict):
                continue
            rep_id = data.get("report_id") or f.stem
            diag_id = data.get("diagnosis_id") or rep_id
            ts = data.get("timestamp") or data.get("execution_timestamp") or ""
            health = data.get("health_classification") or data.get("overall_network_health") or "UNKNOWN"
            fault = data.get("fault_detected", False)
            summary = data.get("summary") or ""
            rc = data.get("probable_root_cause") or {}
            rc_title = rc.get("title", "") if isinstance(rc, dict) else getattr(rc, "title", "")

            reports.append({
                "filename": f.name,
                "filepath": str(f),
                "report_id": rep_id,
                "diagnosis_id": diag_id,
                "timestamp": str(ts),
                "health_classification": str(health).upper(),
                "fault_detected": bool(fault),
                "probable_root_cause": rc_title,
                "summary": summary,
            })
        except Exception:
            # Corrupted report file: skip without crashing
            continue

    # Sort newest first by timestamp or filename
    reports.sort(key=lambda r: (r["timestamp"], r["filename"]), reverse=True)
    return reports


def load_saved_report(
    identifier: str, reports_dir: Union[str, Path]
) -> Tuple[Optional[DiagnosticReport], Optional[str]]:
    """
    Retrieves and parses a complete DiagnosticReport by filename, Report ID, or Diagnosis ID.
    Returns (report, None) on success, or (None, error_message) on failure.
    Handles missing reports, deleted files, or corrupt JSON gracefully.
    """
    p = Path(reports_dir)
    if not p.exists() or not p.is_dir():
        return None, f"Reports directory '{reports_dir}' does not exist."

    clean_id = identifier.strip()
    target_file: Optional[Path] = None

    # Check direct filename match
    if (p / clean_id).exists():
        target_file = p / clean_id
    elif (p / f"{clean_id}.json").exists():
        target_file = p / f"{clean_id}.json"
    else:
        # Search by report_id or diagnosis_id within all JSON files
        for f in p.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if (
                    data.get("report_id") == clean_id
                    or data.get("diagnosis_id") == clean_id
                    or f.stem == clean_id
                ):
                    target_file = f
                    break
            except Exception:
                continue

    if not target_file or not target_file.exists():
        return None, f"Report '{identifier}' was not found in history repository."

    try:
        raw_text = target_file.read_text(encoding="utf-8")
        data = json.loads(raw_text)
        report = DiagnosticReport.model_validate(data)
        return report, None
    except json.JSONDecodeError as exc:
        return None, f"Failed to parse report '{target_file.name}': Malformed JSON syntax ({exc})."
    except Exception as exc:
        return None, f"Failed to validate report '{target_file.name}' against schema: {exc}."


def fetch_report_from_api(
    report_id: str,
    base_url: str = "http://localhost:8000",
    timeout: float = 3.0,
) -> Tuple[Optional[DiagnosticReport], Optional[str]]:
    """
    Retrieves a DiagnosticReport from the FastAPI backend with comprehensive error isolation.
    Handles:
    - Server unavailable / ConnectionError
    - Connection timeout
    - HTTP 400 Bad Request
    - HTTP 404 Not Found
    - HTTP 500 Internal Error
    - Malformed non-JSON response
    - Schema validation errors on incomplete payloads
    """
    clean_id = report_id.strip()
    url = f"{base_url.rstrip('/')}/api/reports/{clean_id}"

    try:
        resp = requests.get(url, timeout=timeout)
    except requests.exceptions.ConnectionError:
        return None, f"Unable to connect to NetCoop AI API at {base_url}. Server is offline or unreachable."
    except requests.exceptions.Timeout:
        return None, f"Connection to NetCoop AI API timed out after {timeout:.1f}s."
    except requests.exceptions.RequestException as exc:
        return None, f"Network request to API failed: {exc}"

    if resp.status_code == 404:
        return None, f"Report '{clean_id}' not found on API server (HTTP 404)."
    elif resp.status_code == 400:
        return None, f"API Bad Request (HTTP 400): {resp.text}"
    elif resp.status_code >= 500:
        return None, f"API Server Error (HTTP {resp.status_code}): Internal server failure."
    elif resp.status_code != 200:
        return None, f"API returned unexpected HTTP status {resp.status_code}: {resp.text}"

    # Parse JSON
    try:
        data = resp.json()
    except (ValueError, json.JSONDecodeError):
        return None, "API returned a malformed non-JSON response body."

    # Validate against DiagnosticReport schema
    try:
        report = DiagnosticReport.model_validate(data)
        return report, None
    except Exception as exc:
        return None, f"API report payload failed DiagnosticReport schema validation: {exc}"


def list_reports_from_api(
    base_url: str = "http://localhost:8000",
    timeout: float = 3.0,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Fetches the list of stored diagnostic reports from the FastAPI backend.
    Returns (reports_list, None) or ([], error_message).
    """
    url = f"{base_url.rstrip('/')}/api/reports"
    try:
        resp = requests.get(url, timeout=timeout)
    except requests.exceptions.ConnectionError:
        return [], f"API server is offline at {base_url}."
    except requests.exceptions.Timeout:
        return [], f"API request timed out after {timeout:.1f}s."
    except Exception as exc:
        return [], f"Failed to connect to API: {exc}"

    if resp.status_code != 200:
        return [], f"API error (HTTP {resp.status_code}): {resp.text}"

    try:
        data = resp.json()
        reports = data.get("reports", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        return reports, None
    except Exception as exc:
        return [], f"Failed to parse report listing from API: {exc}"


def diagnose_via_api(
    telemetry: Optional[Union[pd.DataFrame, List[Dict[str, Any]]]] = None,
    scenario_id: Optional[str] = None,
    base_url: str = "http://localhost:8000",
    timeout: float = 30.0,
) -> Tuple[Optional[DiagnosticReport], Optional[str]]:
    """
    Submits a diagnosis request to the FastAPI backend (/api/diagnose).
    Returns (DiagnosticReport, None) on success, or (None, error_message) on failure.
    """
    url = f"{base_url.rstrip('/')}/api/diagnose"
    payload: Dict[str, Any] = {}

    if scenario_id:
        payload["scenario_id"] = scenario_id

    if telemetry is not None:
        if isinstance(telemetry, pd.DataFrame):
            records = telemetry.where(pd.notnull(telemetry), None).to_dict(orient="records")
        elif isinstance(telemetry, list):
            import math
            records = [
                {k: (None if (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) else v) for k, v in r.items()}
                if isinstance(r, dict) else r
                for r in telemetry
            ]
        else:
            records = []
        payload["telemetry"] = records

    try:
        resp = requests.post(url, json=payload, timeout=timeout)
    except requests.exceptions.ConnectionError:
        return None, f"Unable to connect to NetCoop AI API at {base_url}. Backend server is offline."
    except requests.exceptions.Timeout:
        return None, f"Diagnosis request to API timed out after {timeout:.1f}s."
    except requests.exceptions.RequestException as exc:
        return None, f"Network request to diagnosis API failed: {exc}"

    if resp.status_code != 200:
        try:
            err_data = resp.json()
            err_msg = err_data.get("detail") or err_data.get("message") or resp.text
        except Exception:
            err_msg = resp.text
        return None, f"API diagnosis error (HTTP {resp.status_code}): {err_msg}"

    try:
        data = resp.json()
        report = DiagnosticReport.model_validate(data)
        return report, None
    except Exception as exc:
        return None, f"API returned data that failed DiagnosticReport schema validation: {exc}"

