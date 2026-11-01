from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator

from agents.base_agent import BaseAgent
from communication.models import (
    AgentMessage,
    AgentStatus,
    EvidenceItem,
    Finding,
    Severity,
)
from communication.protocol import create_agent_message, create_error_message

logger = logging.getLogger("agent.connectivity_agent")


class ConnectivitySeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ConnectivityStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    INSUFFICIENT_DATA = "insufficient_data"


class ConnectivityThresholds(BaseModel):
    """
    Configurable connectivity thresholds for DNS, DHCP, Wi-Fi RF, and link state.
    Can be configured at initialization without modifying the agent's source code.
    """
    model_config = ConfigDict(populate_by_name=True)

    # DNS Latency (ms)
    dns_latency_warn_ms: float = Field(default=100.0, ge=0.0, description="Warning threshold for DNS latency")
    dns_latency_crit_ms: float = Field(default=300.0, ge=0.0, description="Critical threshold for DNS latency")

    # Wi-Fi RSSI (dBm)
    wifi_rssi_warn_dbm: float = Field(default=-60.0, le=0.0, description="Below this is warning for Wi-Fi RSSI")
    wifi_rssi_crit_dbm: float = Field(default=-75.0, le=0.0, description="Below this is critical for Wi-Fi RSSI")
    wifi_snr_warn_db: float = Field(default=18.0, ge=0.0, description="Warning threshold for Wi-Fi SNR")

    # DNS Status Mappings
    dns_status_healthy: List[str] = Field(
        default_factory=lambda: ["success", "ok", "resolved"],
        description="DNS status values representing successful resolution",
    )
    dns_status_failed: List[str] = Field(
        default_factory=lambda: ["failed", "servfail", "refused", "nxdomain", "error"],
        description="DNS status values representing server resolution failure",
    )
    dns_status_timeout: List[str] = Field(
        default_factory=lambda: ["timeout"],
        description="DNS status values representing timeout",
    )

    # DHCP Status Mappings
    dhcp_status_healthy: List[str] = Field(
        default_factory=lambda: ["bound", "success", "renewed", "ok"],
        description="DHCP status values representing successful lease assignment",
    )
    dhcp_status_failed: List[str] = Field(
        default_factory=lambda: ["failed", "exhausted", "nack", "error"],
        description="DHCP status values representing allocation failure",
    )
    dhcp_status_timeout: List[str] = Field(
        default_factory=lambda: ["timeout"],
        description="DHCP status values representing lease timeout",
    )

    # Interface/Link Status Mappings
    link_status_healthy: List[str] = Field(
        default_factory=lambda: ["up", "connected", "active"],
        description="Link status values representing operational connectivity",
    )
    link_status_critical: List[str] = Field(
        default_factory=lambda: ["down", "disconnected", "failed", "flapping"],
        description="Link status values representing physical/logical disconnection",
    )


class ConnectivityFinding(BaseModel):
    """
    Structured connectivity finding with evidence, diagnostic explanation, and probable impact.
    Strictly adheres to Milestone 5 requirements and provides interoperability with global Finding models.
    """
    model_config = ConfigDict(populate_by_name=True)

    finding_id: str = Field(default_factory=lambda: f"FND-CONN-{uuid.uuid4().hex[:6].upper()}")
    agent_id: str = Field(default="connectivity_agent")
    device_id: Optional[str] = Field(default=None, description="Identifier of affected device")
    metric: str = Field(..., description="Name of the evaluated connectivity metric")
    observed_value: Any = Field(..., description="Observed value or state")
    threshold: Any = Field(..., description="Configured normal threshold or expected baseline")
    severity: str = Field(..., description="Severity level: info, warning, critical")
    evidence: str = Field(..., description="Factual evidence statement describing observation")
    explanation: str = Field(..., description="Diagnostic reasoning explaining causal mechanics")
    probable_impact: str = Field(..., description="Potential operational impact on network connectivity")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Compatibility fields for global Finding schema and correlation agent
    category: str = Field(default="CONNECTIVITY")
    title: str = Field(default="")
    description: str = Field(default="")
    affected_devices: List[str] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        try:
            val = float(v)
            return max(0.0, min(1.0, val))
        except (ValueError, TypeError):
            return 0.50

    def model_post_init(self, __context: Any) -> None:
        if not self.title:
            dev_str = f" on {self.device_id}" if self.device_id else ""
            self.title = f"[{self.severity.upper()}] {self.metric.replace('_', ' ').title()}{dev_str}"
        if not self.description:
            self.description = f"{self.evidence} {self.explanation}"
        if self.device_id and not self.affected_devices:
            self.affected_devices = [self.device_id]


class ConnectivityAgentResponse(BaseModel):
    """
    Structured output response for the Network Connectivity Agent.
    Contains Milestone 5 specific fields, per-device summaries, and communication protocol interoperability.
    """
    model_config = ConfigDict(populate_by_name=True)

    agent_id: str = Field(default="connectivity_agent")
    task_id: str = Field(...)
    status: Union[AgentStatus, str] = Field(
        default=AgentStatus.SUCCESS,
        description="Execution status conforming to AgentStatus enum or string",
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    analyzed_device_count: int = Field(default=0)
    findings: List[ConnectivityFinding] = Field(default_factory=list)
    device_summaries: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    overall_status: str = Field(
        default="healthy",
        description="Overall connectivity status: healthy, degraded, critical, insufficient_data",
    )
    summary: str = Field(default="")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    errors: List[str] = Field(default_factory=list)

    # Protocol & Orchestrator compatibility fields
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    evidence: List[EvidenceItem] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        try:
            val = float(v)
            return max(0.0, min(1.0, val))
        except (ValueError, TypeError):
            return 0.50

    def to_agent_message(self) -> AgentMessage:
        """Adapts response to the global AgentMessage model for orchestrator communication."""
        global_findings: List[Finding] = []
        for cf in self.findings:
            sev_str = cf.severity.lower()
            if sev_str == "critical":
                sev = Severity.CRITICAL
            elif sev_str == "warning":
                sev = Severity.HIGH
            else:
                sev = Severity.INFO

            global_findings.append(
                Finding(
                    finding_id=cf.finding_id,
                    category=cf.category or "CONNECTIVITY",
                    title=cf.title,
                    description=cf.description,
                    severity=sev,
                    affected_devices=cf.affected_devices,
                    metric_name=cf.metric,
                    observed_value=cf.observed_value,
                    threshold_value=cf.threshold,
                    source_agent=self.agent_id,
                    interface_name=getattr(cf, "interface_name", None),
                    finding_type="OBSERVED_EVIDENCE",
                    timestamp=self.timestamp,
                    metrics={
                        "observed_value": cf.observed_value,
                        "threshold": str(cf.threshold),
                        "metric": cf.metric,
                        "confidence": cf.confidence,
                        **cf.metrics,
                    },
                )
            )

        status_enum = AgentStatus.SUCCESS
        if self.overall_status == ConnectivityStatus.INSUFFICIENT_DATA.value:
            status_enum = AgentStatus.INSUFFICIENT_DATA
        elif self.errors and not self.findings:
            status_enum = AgentStatus.ERROR
        elif self.errors:
            status_enum = AgentStatus.WARNING

        meta = dict(self.metadata)
        meta.update({
            "overall_connectivity_status": self.overall_status,
            "analyzed_device_count": self.analyzed_device_count,
            "device_summaries": self.device_summaries,
            "summary": self.summary,
        })

        return AgentMessage(
            message_id=self.message_id,
            task_id=self.task_id,
            agent_id=self.agent_id,
            status=status_enum,
            timestamp=self.timestamp,
            findings=global_findings,
            evidence=self.evidence,
            confidence=self.confidence,
            errors=self.errors,
            metadata=meta,
        )


class ConnectivityAgent(BaseAgent):
    """
    Upgraded, production-quality Network Connectivity Diagnosis Agent.
    Evaluates DNS resolution status and query latency, DHCP lease allocation,
    wireless RF signal strength (RSSI/SNR), and end-to-end interface/link connectivity.
    """

    def __init__(self, thresholds: Optional[ConnectivityThresholds] = None):
        super().__init__(
            agent_id="connectivity_agent",
            name="Network Connectivity Specialist",
            description="Evaluates DNS naming, DHCP IP addressing, Wi-Fi RF levels, and host link reachability.",
        )
        self.thresholds = thresholds or ConnectivityThresholds()

    # -------------------------------------------------------------------------
    # MAIN AGENT EXECUTION INTERFACE
    # -------------------------------------------------------------------------

    def execute(
        self,
        task_id: str,
        telemetry: Union[pd.DataFrame, List[Any], Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
    ) -> ConnectivityAgentResponse:
        """
        Executes end-to-end connectivity diagnostics on telemetry input.
        Returns a structured ConnectivityAgentResponse compatible with AgentMessage.
        """
        start_time = time.perf_counter()
        context = context or {}
        active_thresholds = context.get("thresholds", self.thresholds)

        valid_records, validation_errors = self._normalize_and_validate(telemetry)

        # Empty / completely invalid data handling
        if not valid_records:
            exec_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            errors = [str(e) for e in validation_errors] or ["No telemetry records provided for connectivity evaluation."]
            return ConnectivityAgentResponse(
                agent_id=self.agent_id,
                task_id=task_id,
                status=AgentStatus.INSUFFICIENT_DATA,
                timestamp=datetime.now(timezone.utc),
                analyzed_device_count=0,
                findings=[
                    ConnectivityFinding(
                        metric="connectivity_telemetry",
                        observed_value=0,
                        threshold=">= 1 record",
                        severity=ConnectivitySeverity.INFO.value,
                        evidence="Telemetry dataset is empty or contains no valid connectivity records.",
                        explanation="Connectivity health cannot be evaluated without valid metric samples.",
                        probable_impact="Unable to assess DNS, DHCP, wireless, or link reachability.",
                        confidence=0.0,
                        title="Empty or Invalid Connectivity Telemetry",
                    )
                ],
                device_summaries={},
                overall_status=ConnectivityStatus.INSUFFICIENT_DATA.value,
                summary="Telemetry dataset is empty or contains no valid connectivity records.",
                confidence=0.0,
                errors=errors,
                metadata={"execution_time_ms": exec_time_ms, "record_count": 0},
            )

        df = pd.DataFrame(valid_records)

        # Analyze dataset across devices
        findings, evidence_items, confidence, analysis_errors = self.analyze(
            df=df,
            context={"thresholds": active_thresholds, **context},
        )

        all_errors = list(analysis_errors)
        if validation_errors:
            all_errors.extend([str(e) for e in validation_errors])

        analyzed_devices = df["device_id"].unique().tolist() if "device_id" in df.columns else ["unknown"]

        # Build per-device summaries
        device_summaries = self._build_device_summaries(df, findings, active_thresholds)

        # Determine overall connectivity status
        has_critical = any(f.severity.lower() == ConnectivitySeverity.CRITICAL.value for f in findings)
        has_warning = any(f.severity.lower() == ConnectivitySeverity.WARNING.value for f in findings)

        if has_critical:
            overall_status = ConnectivityStatus.CRITICAL.value
        elif has_warning:
            overall_status = ConnectivityStatus.DEGRADED.value
        else:
            overall_status = ConnectivityStatus.HEALTHY.value

        exec_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        summary = self._formulate_summary(overall_status, findings, analyzed_devices, len(df))

        status_enum = AgentStatus.SUCCESS
        if all_errors and not findings:
            status_enum = AgentStatus.ERROR
        elif all_errors:
            status_enum = AgentStatus.WARNING

        return ConnectivityAgentResponse(
            agent_id=self.agent_id,
            task_id=task_id,
            status=status_enum,
            timestamp=datetime.now(timezone.utc),
            analyzed_device_count=len(analyzed_devices),
            findings=findings,
            device_summaries=device_summaries,
            overall_status=overall_status,
            summary=summary,
            confidence=confidence,
            errors=all_errors,
            evidence=evidence_items,
            metadata={
                "execution_time_ms": exec_time_ms,
                "record_count": len(df),
                "agent_name": self.name,
            },
        )

    def analyze_telemetry(
        self,
        telemetry: Any,
        task_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        thresholds: Optional[ConnectivityThresholds] = None,
    ) -> ConnectivityAgentResponse:
        """Convenience direct invocation interface with optional threshold overrides."""
        ctx = dict(context or {})
        if thresholds:
            ctx["thresholds"] = thresholds
        t_id = task_id or f"TASK-CONN-{uuid.uuid4().hex[:8].upper()}"
        return self.execute(t_id, telemetry, context=ctx)

    # -------------------------------------------------------------------------
    # CORE DOMAIN ANALYSIS (DataFrame -> Findings, Evidence, Confidence, Errors)
    # -------------------------------------------------------------------------

    def analyze(
        self,
        df: pd.DataFrame,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[ConnectivityFinding], List[EvidenceItem], float, List[str]]:
        """
        Analyzes normalized DataFrame per device against active thresholds.
        Evaluates DNS status/latency, DHCP status/lease, Wi-Fi RSSI, and link connectivity.
        """
        context = context or {}
        active_thresholds = context.get("thresholds", self.thresholds)

        findings: List[ConnectivityFinding] = []
        evidence_items: List[EvidenceItem] = []
        errors: List[str] = []

        analyzed_devices = df["device_id"].unique().tolist() if "device_id" in df.columns else ["unknown"]
        device_groups = df.groupby("device_id") if "device_id" in df.columns and len(analyzed_devices) > 1 else [(analyzed_devices[0] if analyzed_devices else None, df)]

        for dev_id, dev_df in device_groups:
            # 1. Evaluate individual metrics
            dns_st = self._analyze_dns_status(dev_df, dev_id, active_thresholds, findings, evidence_items)
            dns_lat = self._analyze_dns_latency(dev_df, dev_id, active_thresholds, findings, evidence_items)
            dhcp_st = self._analyze_dhcp_status(dev_df, dev_id, active_thresholds, findings, evidence_items)
            wifi_val = self._analyze_wifi_rssi(dev_df, dev_id, active_thresholds, findings, evidence_items)
            self._analyze_wifi_snr(dev_df, dev_id, active_thresholds, evidence_items)
            link_st = self._analyze_link_and_reachability(dev_df, dev_id, active_thresholds, findings, evidence_items)

            # 2. Correlate indicators for this device
            self._correlate_device_indicators(
                dev_id=dev_id,
                dns_status=dns_st,
                dns_latency=dns_lat,
                dhcp_status=dhcp_st,
                wifi_rssi=wifi_val,
                link_status=link_st,
                df=dev_df,
                th=active_thresholds,
                findings=findings,
                evidence_items=evidence_items,
            )

        # 3. Overall confidence calculation
        if not findings:
            confidence = 0.95 if len(df) >= 5 else 0.70
            findings.append(
                ConnectivityFinding(
                    metric="connectivity_overall",
                    observed_value="healthy",
                    threshold="all operational limits",
                    severity=ConnectivitySeverity.INFO.value,
                    title="Healthy Connectivity & Core Services",
                    evidence=f"DNS resolution, DHCP lease acquisition, wireless RSSI, and link status are operating normally across {len(analyzed_devices)} device(s).",
                    explanation="No naming, addressing, wireless attenuation, or physical link disconnection faults detected.",
                    probable_impact="End-to-end IP reachability and application communication operate nominally.",
                    confidence=confidence,
                    device_id=analyzed_devices[0] if len(analyzed_devices) == 1 else None,
                    affected_devices=analyzed_devices,
                    metrics={"evaluated_records": len(df)},
                )
            )
        else:
            conf_scores = [f.confidence for f in findings]
            avg_conf = float(np.mean(conf_scores)) if conf_scores else 0.85
            sample_boost = 0.05 if len(df) >= 8 else 0.0
            confidence = min(0.99, max(0.60, round(avg_conf + sample_boost, 2)))

        return findings, evidence_items, confidence, errors

    # -------------------------------------------------------------------------
    # SPECIFIC METRIC ANALYZERS
    # -------------------------------------------------------------------------

    def _analyze_dns_status(
        self,
        df: pd.DataFrame,
        device_id: Optional[str],
        th: ConnectivityThresholds,
        findings: List[ConnectivityFinding],
        evidence_items: List[EvidenceItem],
    ) -> Optional[str]:
        col = "dns_status" if "dns_status" in df.columns else ("dns_resolution_status" if "dns_resolution_status" in df.columns else None)
        if not col or not df[col].notna().any():
            return None

        statuses = df[col].dropna().astype(str).str.lower().unique().tolist()
        dev_label = f"Device '{device_id}': " if device_id else ""
        dev_str = f" on {device_id}" if device_id else ""

        crit_failed = [s for s in statuses if s in [x.lower() for x in th.dns_status_failed]]
        crit_timeout = [s for s in statuses if s in [x.lower() for x in th.dns_status_timeout]]

        if crit_timeout:
            evidence = f"{dev_label}DNS resolution queries timed out completely ({', '.join(crit_timeout)})."
            explanation = "Upstream DNS server or recursive resolver is unreachable or not responding."
            impact = "Client applications cannot resolve hostnames to IP addresses, causing application connection failure."
            findings.append(
                ConnectivityFinding(
                    metric="dns_status",
                    observed_value=", ".join(crit_timeout),
                    threshold="success",
                    severity=ConnectivitySeverity.CRITICAL.value,
                    title=f"DNS Resolution Failure / Server Outage{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.96,
                    device_id=device_id,
                    metrics={"dns_status": crit_timeout},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="dns_resolution_status",
                    observed_value=", ".join(crit_timeout),
                    threshold="success",
                    device_id=device_id,
                    details=evidence,
                )
            )
            return crit_timeout[0]
        elif crit_failed:
            evidence = f"{dev_label}DNS resolution queries failed with status: {', '.join(crit_failed)}."
            explanation = "DNS nameserver returned error response (SERVFAIL/REFUSED/NXDOMAIN), indicating zone failure or resolver misconfiguration."
            impact = "Domain lookups fail, breaking web browsing, API integrations, and cloud services."
            findings.append(
                ConnectivityFinding(
                    metric="dns_status",
                    observed_value=", ".join(crit_failed),
                    threshold="success",
                    severity=ConnectivitySeverity.CRITICAL.value,
                    title=f"DNS Resolution Failure / Server Outage{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.95,
                    device_id=device_id,
                    metrics={"dns_status": crit_failed},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="dns_resolution_status",
                    observed_value=", ".join(crit_failed),
                    threshold="success",
                    device_id=device_id,
                    details=evidence,
                )
            )
            return crit_failed[0]

        return statuses[0] if statuses else None

    def _analyze_dns_latency(
        self,
        df: pd.DataFrame,
        device_id: Optional[str],
        th: ConnectivityThresholds,
        findings: List[ConnectivityFinding],
        evidence_items: List[EvidenceItem],
    ) -> Optional[float]:
        if "dns_latency_ms" not in df.columns or not df["dns_latency_ms"].notna().any():
            return None

        valid = df["dns_latency_ms"].dropna()
        max_lat = float(valid.max())
        mean_lat = float(valid.mean())
        dev_label = f"Device '{device_id}': " if device_id else ""
        dev_str = f" on {device_id}" if device_id else ""

        if max_lat > th.dns_latency_crit_ms:
            evidence = f"{dev_label}DNS query latency severely elevated to {max_lat:.1f}ms (mean: {mean_lat:.1f}ms), breaching critical threshold of {th.dns_latency_crit_ms}ms."
            explanation = "High round-trip delay to DNS nameserver or resolver query queue congestion."
            impact = "Severe delay in connection establishment for web and cloud applications."
            findings.append(
                ConnectivityFinding(
                    metric="dns_latency_ms",
                    observed_value=round(max_lat, 1),
                    threshold=f"<= {th.dns_latency_warn_ms}ms (warn), <= {th.dns_latency_crit_ms}ms (crit)",
                    severity=ConnectivitySeverity.CRITICAL.value,
                    title=f"Critical DNS Query Delay{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.93 if len(valid) >= 3 else 0.85,
                    device_id=device_id,
                    metrics={"max_dns_latency_ms": round(max_lat, 1), "mean_dns_latency_ms": round(mean_lat, 1)},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="dns_latency_ms",
                    observed_value=round(max_lat, 1),
                    threshold=th.dns_latency_crit_ms,
                    unit="ms",
                    device_id=device_id,
                    details=evidence,
                )
            )
        elif max_lat > th.dns_latency_warn_ms:
            evidence = f"{dev_label}DNS query latency elevated to {max_lat:.1f}ms (mean: {mean_lat:.1f}ms), exceeding warning threshold {th.dns_latency_warn_ms}ms."
            explanation = "Elevated query lookup time to upstream nameserver."
            impact = "Noticeable lag in initial application connection setups."
            findings.append(
                ConnectivityFinding(
                    metric="dns_latency_ms",
                    observed_value=round(max_lat, 1),
                    threshold=f"<= {th.dns_latency_warn_ms}ms",
                    severity=ConnectivitySeverity.WARNING.value,
                    title=f"Degraded DNS Response Time{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.85,
                    device_id=device_id,
                    metrics={"max_dns_latency_ms": round(max_lat, 1), "mean_dns_latency_ms": round(mean_lat, 1)},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="dns_latency_ms",
                    observed_value=round(max_lat, 1),
                    threshold=th.dns_latency_warn_ms,
                    unit="ms",
                    device_id=device_id,
                    details=evidence,
                )
            )

        return max_lat

    def _analyze_dhcp_status(
        self,
        df: pd.DataFrame,
        device_id: Optional[str],
        th: ConnectivityThresholds,
        findings: List[ConnectivityFinding],
        evidence_items: List[EvidenceItem],
    ) -> Optional[str]:
        if "dhcp_status" not in df.columns or not df["dhcp_status"].notna().any():
            return None

        statuses = df["dhcp_status"].dropna().astype(str).str.lower().unique().tolist()
        dev_label = f"Device '{device_id}': " if device_id else ""
        dev_str = f" on {device_id}" if device_id else ""

        crit_timeout = [s for s in statuses if s in [x.lower() for x in th.dhcp_status_timeout]]
        crit_failed = [s for s in statuses if s in [x.lower() for x in th.dhcp_status_failed]]

        if crit_timeout:
            evidence = f"{dev_label}DHCP lease request timed out ({', '.join(crit_timeout)})."
            explanation = "DHCP server or relay agent did not respond to DHCPDISCOVER/DHCPREQUEST packets."
            impact = "Client cannot obtain dynamic IP address configuration and falls back to self-assigned link-local IP (169.254.x.x)."
            findings.append(
                ConnectivityFinding(
                    metric="dhcp_status",
                    observed_value=", ".join(crit_timeout),
                    threshold="bound",
                    severity=ConnectivitySeverity.CRITICAL.value,
                    title=f"DHCP Pool Exhaustion / Allocation Failure{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.96,
                    device_id=device_id,
                    metrics={"dhcp_status": crit_timeout},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="dhcp_status",
                    observed_value=", ".join(crit_timeout),
                    threshold="bound",
                    device_id=device_id,
                    details=evidence,
                )
            )
            return crit_timeout[0]
        elif crit_failed:
            is_exhausted = any(s == "exhausted" for s in crit_failed)
            evidence = f"{dev_label}DHCP lease allocation failed with status: {', '.join(crit_failed)}."
            explanation = "DHCP address scope exhausted or DHCP server rejected assignment (NAK)." if is_exhausted else "DHCP server encountered allocation failure."
            impact = "Endpoints fail to acquire IP addresses, disconnecting them from the local LAN and internet."
            findings.append(
                ConnectivityFinding(
                    metric="dhcp_status",
                    observed_value=", ".join(crit_failed),
                    threshold="bound",
                    severity=ConnectivitySeverity.CRITICAL.value,
                    title=f"DHCP Pool Exhaustion / Allocation Failure{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.95,
                    device_id=device_id,
                    metrics={"dhcp_status": crit_failed},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="dhcp_status",
                    observed_value=", ".join(crit_failed),
                    threshold="bound",
                    device_id=device_id,
                    details=evidence,
                )
            )
            return crit_failed[0]

        return statuses[0] if statuses else None

    def _analyze_wifi_rssi(
        self,
        df: pd.DataFrame,
        device_id: Optional[str],
        th: ConnectivityThresholds,
        findings: List[ConnectivityFinding],
        evidence_items: List[EvidenceItem],
    ) -> Optional[float]:
        col = "wifi_signal_dbm" if "wifi_signal_dbm" in df.columns else ("wifi_rssi_dbm" if "wifi_rssi_dbm" in df.columns else None)
        if not col or not df[col].notna().any():
            return None

        valid = df[col].dropna()
        min_rssi = float(valid.min())
        mean_rssi = float(valid.mean())
        dev_label = f"Device '{device_id}': " if device_id else ""
        dev_str = f" on {device_id}" if device_id else ""

        if min_rssi < th.wifi_rssi_crit_dbm:
            evidence = f"{dev_label}Wi-Fi received signal strength (RSSI) degraded critically to {min_rssi:.1f} dBm (mean: {mean_rssi:.1f} dBm), below critical threshold {th.wifi_rssi_crit_dbm} dBm."
            explanation = "Severe wireless RF signal attenuation, extreme distance from access point, or dense physical obstructions (walls/metal)."
            impact = "Frequent 802.11 frame loss, modulation rate drop to minimum, and recurrent wireless disconnections."
            findings.append(
                ConnectivityFinding(
                    metric="wifi_signal_dbm",
                    observed_value=round(min_rssi, 1),
                    threshold=f">= {th.wifi_rssi_warn_dbm} dBm (good), >= {th.wifi_rssi_crit_dbm} dBm (crit)",
                    severity=ConnectivitySeverity.CRITICAL.value,
                    title=f"Severe Wireless Signal Attenuation (Weak Wi-Fi){dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.94 if len(valid) >= 3 else 0.88,
                    device_id=device_id,
                    metrics={"min_rssi_dbm": round(min_rssi, 1), "mean_rssi_dbm": round(mean_rssi, 1)},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="wifi_rssi_dbm",
                    observed_value=round(min_rssi, 1),
                    threshold=th.wifi_rssi_crit_dbm,
                    unit="dBm",
                    device_id=device_id,
                    details=evidence,
                )
            )
        elif min_rssi < th.wifi_rssi_warn_dbm:
            evidence = f"{dev_label}Wi-Fi received signal strength (RSSI) degraded to {min_rssi:.1f} dBm (mean: {mean_rssi:.1f} dBm), below recommended threshold {th.wifi_rssi_warn_dbm} dBm."
            explanation = "Marginal wireless coverage or RF path attenuation."
            impact = "Modest drop in wireless PHY rate and occasional retransmissions."
            findings.append(
                ConnectivityFinding(
                    metric="wifi_signal_dbm",
                    observed_value=round(min_rssi, 1),
                    threshold=f">= {th.wifi_rssi_warn_dbm} dBm",
                    severity=ConnectivitySeverity.WARNING.value,
                    title=f"Degraded Wi-Fi Signal Strength{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.86,
                    device_id=device_id,
                    metrics={"min_rssi_dbm": round(min_rssi, 1), "mean_rssi_dbm": round(mean_rssi, 1)},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="wifi_rssi_dbm",
                    observed_value=round(min_rssi, 1),
                    threshold=th.wifi_rssi_warn_dbm,
                    unit="dBm",
                    device_id=device_id,
                    details=evidence,
                )
            )

        return min_rssi

    def _analyze_wifi_snr(
        self,
        df: pd.DataFrame,
        device_id: Optional[str],
        th: ConnectivityThresholds,
        evidence_items: List[EvidenceItem],
    ) -> Optional[float]:
        if "wifi_snr_db" not in df.columns or not df["wifi_snr_db"].notna().any():
            return None

        valid = df["wifi_snr_db"].dropna()
        min_snr = float(valid.min())
        dev_label = f"Device '{device_id}': " if device_id else ""

        if min_snr < th.wifi_snr_warn_db:
            evidence = f"{dev_label}Wireless Signal-to-Noise Ratio (SNR) fell to {min_snr:.1f} dB, indicating high RF noise or interference."
            evidence_items.append(
                EvidenceItem(
                    metric_name="wifi_snr_db",
                    observed_value=round(min_snr, 1),
                    threshold=th.wifi_snr_warn_db,
                    unit="dB",
                    device_id=device_id,
                    details=evidence,
                )
            )

        return min_snr

    def _analyze_link_and_reachability(
        self,
        df: pd.DataFrame,
        device_id: Optional[str],
        th: ConnectivityThresholds,
        findings: List[ConnectivityFinding],
        evidence_items: List[EvidenceItem],
    ) -> Optional[str]:
        dev_label = f"Device '{device_id}': " if device_id else ""
        dev_str = f" on {device_id}" if device_id else ""

        # 1. Interface status
        if "interface_status" in df.columns and df["interface_status"].notna().any():
            statuses = df["interface_status"].dropna().astype(str).str.lower().unique().tolist()
            down_states = [s for s in statuses if s in [x.lower() for x in th.link_status_critical]]
            if down_states:
                evidence = f"{dev_label}Network interface link reported in disconnected state: {', '.join(down_states)}."
                explanation = "Physical or logical network interface is down or disabled."
                impact = "No layer 2/3 traffic can be transmitted across this interface."
                findings.append(
                    ConnectivityFinding(
                        metric="link_status",
                        observed_value=", ".join(down_states),
                        threshold="up",
                        severity=ConnectivitySeverity.CRITICAL.value,
                        title=f"Interface Link Disconnected{dev_str}",
                        evidence=evidence,
                        explanation=explanation,
                        probable_impact=impact,
                        confidence=0.96,
                        device_id=device_id,
                        metrics={"interface_status": down_states},
                    )
                )
                evidence_items.append(
                    EvidenceItem(
                        metric_name="interface_status",
                        observed_value=", ".join(down_states),
                        threshold="up",
                        device_id=device_id,
                        details=evidence,
                    )
                )
                return down_states[0]

        # 2. End-to-end connectivity status
        if "connectivity_status" in df.columns and df["connectivity_status"].notna().any():
            c_states = df["connectivity_status"].dropna().astype(str).str.lower().unique().tolist()
            disconnected = [s for s in c_states if s in ["disconnected", "down", "failed"]]
            degraded = [s for s in c_states if s in ["degraded"]]
            if disconnected:
                evidence = f"{dev_label}End-to-end reachability test reported: {', '.join(disconnected)}."
                explanation = "Network path is unreachable; ping/probe packets to destination gateway or peer failed."
                impact = "Total loss of network reachability for this endpoint."
                findings.append(
                    ConnectivityFinding(
                        metric="connectivity_status",
                        observed_value=", ".join(disconnected),
                        threshold="connected",
                        severity=ConnectivitySeverity.CRITICAL.value,
                        title=f"Loss of Network Reachability{dev_str}",
                        evidence=evidence,
                        explanation=explanation,
                        probable_impact=impact,
                        confidence=0.95,
                        device_id=device_id,
                        metrics={"connectivity_status": disconnected},
                    )
                )
                evidence_items.append(
                    EvidenceItem(
                        metric_name="connectivity_status",
                        observed_value=", ".join(disconnected),
                        threshold="connected",
                        device_id=device_id,
                        details=evidence,
                    )
                )
                return disconnected[0]
            elif degraded:
                evidence = f"{dev_label}End-to-end reachability test reported degraded state."
                explanation = "Intermittent loss or high jitter on synthetic health probes."
                impact = "Unstable application performance."
                findings.append(
                    ConnectivityFinding(
                        metric="connectivity_status",
                        observed_value="degraded",
                        threshold="connected",
                        severity=ConnectivitySeverity.WARNING.value,
                        title=f"Degraded Network Reachability{dev_str}",
                        evidence=evidence,
                        explanation=explanation,
                        probable_impact=impact,
                        confidence=0.88,
                        device_id=device_id,
                        metrics={"connectivity_status": ["degraded"]},
                    )
                )
                evidence_items.append(
                    EvidenceItem(
                        metric_name="connectivity_status",
                        observed_value="degraded",
                        threshold="connected",
                        device_id=device_id,
                        details=evidence,
                    )
                )
                return "degraded"

        return "connected"

    # -------------------------------------------------------------------------
    # MULTI-METRIC DIAGNOSTIC REASONING & CORRELATION
    # -------------------------------------------------------------------------

    def _correlate_device_indicators(
        self,
        dev_id: Optional[str],
        dns_status: Optional[str],
        dns_latency: Optional[float],
        dhcp_status: Optional[str],
        wifi_rssi: Optional[float],
        link_status: Optional[str],
        df: pd.DataFrame,
        th: ConnectivityThresholds,
        findings: List[ConnectivityFinding],
        evidence_items: List[EvidenceItem],
    ) -> None:
        """
        Synthesizes composite causal findings when multiple interrelated connectivity indicators correlate.
        Clearly distinguishes observed failures from inferred causes.
        """
        dev_str = f" on {dev_id}" if dev_id else ""
        dev_label = f"Device '{dev_id}': " if dev_id else ""

        # 1. DNS Failure + High DNS Latency => Severe DNS Service Degradation
        if dns_status and dns_latency is not None:
            is_dns_failed = dns_status.lower() in [x.lower() for x in th.dns_status_failed + th.dns_status_timeout]
            if is_dns_failed and dns_latency > th.dns_latency_warn_ms:
                evidence = (
                    f"{dev_label}Observed DNS resolution failure ('{dns_status}') concurrent with "
                    f"elevated query latency ({dns_latency:.1f}ms)."
                )
                explanation = (
                    "Upstream DNS infrastructure is experiencing both server timeouts and severe processing lag. "
                    "Inferred cause: resolver overload, authoritative nameserver failure, or upstream transit loss."
                )
                impact = "Complete failure of hostname-dependent services with cascading client application timeouts."
                findings.append(
                    ConnectivityFinding(
                        metric="composite_dns_degradation",
                        observed_value=f"Status: {dns_status}, Latency: {dns_latency:.1f}ms",
                        threshold=f"Status: success, Latency <= {th.dns_latency_warn_ms}ms",
                        severity=ConnectivitySeverity.CRITICAL.value,
                        title=f"Severe DNS Service Degradation & Outage{dev_str}",
                        evidence=evidence,
                        explanation=explanation,
                        probable_impact=impact,
                        confidence=0.96,
                        device_id=dev_id,
                        metrics={"dns_status": dns_status, "dns_latency_ms": dns_latency},
                    )
                )

        # 2. DHCP Failure + Unavailable Lease => DHCP Pool Exhaustion
        if dhcp_status:
            is_dhcp_failed = dhcp_status.lower() in [x.lower() for x in th.dhcp_status_failed + th.dhcp_status_timeout]
            has_lease_unavailable = False
            for lease_col in ["dhcp_lease_available", "dhcp_lease_status"]:
                if lease_col in df.columns and df[lease_col].notna().any():
                    val = str(df[lease_col].dropna().iloc[-1]).lower()
                    if val in ["false", "0", "unavailable", "exhausted", "none"]:
                        has_lease_unavailable = True
                        break

            if is_dhcp_failed and has_lease_unavailable:
                evidence = (
                    f"{dev_label}DHCP lease failure ('{dhcp_status}') with explicit lease scope unavailability."
                )
                explanation = (
                    "DHCP address pool on server/scope is completely exhausted or DHCPDISCOVER packets dropped. "
                    "Inferred cause: IP address scope too small for client density or lease duration too long."
                )
                impact = "New endpoints cannot join network; existing devices cannot renew leases."
                findings.append(
                    ConnectivityFinding(
                        metric="composite_dhcp_allocation_failure",
                        observed_value=f"Status: {dhcp_status}, LeaseAvailable: False",
                        threshold="Status: bound, LeaseAvailable: True",
                        severity=ConnectivitySeverity.CRITICAL.value,
                        title=f"DHCP Scope Exhaustion & Allocation Failure{dev_str}",
                        evidence=evidence,
                        explanation=explanation,
                        probable_impact=impact,
                        confidence=0.97,
                        device_id=dev_id,
                        metrics={"dhcp_status": dhcp_status, "lease_available": False},
                    )
                )

        # 3. Weak Wi-Fi RSSI + Packet Loss => Wireless Signal Attenuation & RF Loss
        if wifi_rssi is not None:
            has_loss = False
            max_loss = 0.0
            for loss_col in ["packet_loss_percent", "packet_loss_pct"]:
                if loss_col in df.columns and df[loss_col].notna().any():
                    max_loss = float(df[loss_col].dropna().max())
                    if max_loss > 1.0:
                        has_loss = True
                        break

            if wifi_rssi < th.wifi_rssi_warn_dbm and has_loss:
                evidence = (
                    f"{dev_label}Sub-optimal Wi-Fi RSSI ({wifi_rssi:.1f} dBm) correlating with "
                    f"{max_loss:.1f}% packet transmission loss."
                )
                explanation = (
                    "Weak RF link power directly causes physical layer demodulation failures and 802.11 retries. "
                    "Inferred cause: excessive path loss, distance from AP, or co-channel interference."
                )
                impact = "Wireless client experiences high latency jitter, connection stalls, and intermittent VoIP drops."
                findings.append(
                    ConnectivityFinding(
                        metric="composite_wireless_degradation",
                        observed_value=f"RSSI: {wifi_rssi:.1f} dBm, Loss: {max_loss:.1f}%",
                        threshold=f"RSSI >= {th.wifi_rssi_warn_dbm} dBm, Loss <= 1%",
                        severity=ConnectivitySeverity.CRITICAL.value if (wifi_rssi < th.wifi_rssi_crit_dbm or max_loss > 5.0) else ConnectivitySeverity.WARNING.value,
                        title=f"Wireless RF Attenuation with Associated Packet Loss{dev_str}",
                        evidence=evidence,
                        explanation=explanation,
                        probable_impact=impact,
                        confidence=0.94,
                        device_id=dev_id,
                        metrics={"wifi_rssi_dbm": wifi_rssi, "packet_loss_pct": max_loss},
                    )
                )

        # 4. Link Down + Disconnected Reachability => Complete Link Connectivity Failure
        if link_status and link_status.lower() in [x.lower() for x in th.link_status_critical]:
            evidence = (
                f"{dev_label}Physical/logical interface down with loss of host reachability."
            )
            explanation = (
                "Hardware link layer loss or disconnected ethernet medium. "
                "Inferred cause: unplugged cable, failed switch port, or administrative port shutdown."
            )
            impact = "Complete link partition: no inbound or outbound data transmission."
            findings.append(
                ConnectivityFinding(
                    metric="composite_link_failure",
                    observed_value=f"Link: {link_status}",
                    threshold="Link: up",
                    severity=ConnectivitySeverity.CRITICAL.value,
                    title=f"Complete Link Connectivity Failure{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.98,
                    device_id=dev_id,
                    metrics={"link_status": link_status},
                )
            )

    # -------------------------------------------------------------------------
    # SUMMARIES & NORMALIZATION
    # -------------------------------------------------------------------------

    def _build_device_summaries(
        self,
        df: pd.DataFrame,
        findings: List[ConnectivityFinding],
        th: ConnectivityThresholds,
    ) -> Dict[str, Dict[str, Any]]:
        summaries: Dict[str, Dict[str, Any]] = {}
        analyzed_devices = df["device_id"].unique().tolist() if "device_id" in df.columns else ["unknown"]

        for dev in analyzed_devices:
            dev_df = df[df["device_id"] == dev] if "device_id" in df.columns else df
            dev_findings = [f for f in findings if f.device_id == dev or (not f.device_id and len(analyzed_devices) == 1)]

            has_crit = any(f.severity.lower() == ConnectivitySeverity.CRITICAL.value for f in dev_findings)
            has_warn = any(f.severity.lower() == ConnectivitySeverity.WARNING.value for f in dev_findings)

            if has_crit:
                dev_status = ConnectivityStatus.CRITICAL.value
            elif has_warn:
                dev_status = ConnectivityStatus.DEGRADED.value
            else:
                dev_status = ConnectivityStatus.HEALTHY.value

            metrics_summary = {}
            for col in ["dns_status", "dns_resolution_status"]:
                if col in dev_df.columns and dev_df[col].notna().any():
                    metrics_summary["dns_status"] = str(dev_df[col].dropna().iloc[-1])
                    break
            if "dns_latency_ms" in dev_df.columns and dev_df["dns_latency_ms"].notna().any():
                metrics_summary["max_dns_latency_ms"] = round(float(dev_df["dns_latency_ms"].dropna().max()), 1)
            if "dhcp_status" in dev_df.columns and dev_df["dhcp_status"].notna().any():
                metrics_summary["dhcp_status"] = str(dev_df["dhcp_status"].dropna().iloc[-1])
            for col in ["wifi_signal_dbm", "wifi_rssi_dbm"]:
                if col in dev_df.columns and dev_df[col].notna().any():
                    metrics_summary["min_wifi_rssi_dbm"] = round(float(dev_df[col].dropna().min()), 1)
                    break
            for col in ["interface_status", "connectivity_status"]:
                if col in dev_df.columns and dev_df[col].notna().any():
                    metrics_summary["link_status"] = str(dev_df[col].dropna().iloc[-1])
                    break

            summaries[dev] = {
                "device_id": dev,
                "status": dev_status,
                "record_count": len(dev_df),
                "anomaly_count": len([f for f in dev_findings if f.severity != ConnectivitySeverity.INFO.value]),
                "metrics_summary": metrics_summary,
            }

        return summaries

    def _formulate_summary(
        self,
        overall_status: str,
        findings: List[ConnectivityFinding],
        devices: List[str],
        record_count: int,
    ) -> str:
        dev_count = len(devices)
        if overall_status == ConnectivityStatus.HEALTHY.value:
            return f"Connectivity health is nominal across {dev_count} device(s) ({record_count} telemetry samples evaluated). DNS, DHCP, Wi-Fi, and link reachability are normal."

        anomalies = [f"{f.metric} ({f.severity})" for f in findings if f.severity != ConnectivitySeverity.INFO.value]
        return (
            f"Connectivity health assessment: {overall_status.upper()}. "
            f"Detected {len(anomalies)} anomaly/anomalies across {dev_count} device(s): {', '.join(anomalies)}. "
            f"Evaluated {record_count} telemetry samples."
        )

    def _normalize_and_validate(self, telemetry: Any) -> Tuple[List[Dict[str, Any]], List[str]]:
        raw_items: List[Any] = []

        if isinstance(telemetry, pd.DataFrame):
            if telemetry.empty:
                return [], []
            raw_items = telemetry.to_dict(orient="records")
        elif isinstance(telemetry, dict):
            raw_items = [telemetry]
        elif hasattr(telemetry, "model_dump"):
            raw_items = [telemetry.model_dump()]
        elif isinstance(telemetry, list):
            for it in telemetry:
                if hasattr(it, "model_dump"):
                    raw_items.append(it.model_dump())
                elif isinstance(it, dict):
                    raw_items.append(it)
                else:
                    raw_items.append(it)
        else:
            return [], [f"Unsupported telemetry input type: {type(telemetry).__name__}"]

        valid_records: List[Dict[str, Any]] = []
        validation_errors: List[str] = []

        for idx, item in enumerate(raw_items):
            if not isinstance(item, dict):
                validation_errors.append(f"Item #{idx}: Expected dict or TelemetryRecord, got {type(item).__name__}")
                continue

            dev_id = item.get("device_id")
            if not dev_id or not str(dev_id).strip():
                validation_errors.append(f"Item #{idx}: Missing required 'device_id'")
                continue

            item_errors = []

            # Validate DNS latency
            if "dns_latency_ms" in item and item["dns_latency_ms"] is not None:
                try:
                    val = float(item["dns_latency_ms"])
                    if val < 0.0:
                        item_errors.append(f"Item #{idx} ({dev_id}): dns_latency_ms cannot be negative ({val})")
                except (ValueError, TypeError):
                    item_errors.append(f"Item #{idx} ({dev_id}): dns_latency_ms must be numeric")

            # Validate Wi-Fi RSSI
            wifi_key = "wifi_signal_dbm" if "wifi_signal_dbm" in item else "wifi_rssi_dbm"
            if wifi_key in item and item[wifi_key] is not None:
                try:
                    val = float(item[wifi_key])
                    if val < -120.0 or val > 0.0:
                        item_errors.append(f"Item #{idx} ({dev_id}): Wi-Fi RSSI must be in -120 to 0 dBm ({val})")
                except (ValueError, TypeError):
                    item_errors.append(f"Item #{idx} ({dev_id}): Wi-Fi RSSI must be numeric")

            # Validate Wi-Fi SNR
            if "wifi_snr_db" in item and item["wifi_snr_db"] is not None:
                try:
                    val = float(item["wifi_snr_db"])
                    if val < 0.0:
                        item_errors.append(f"Item #{idx} ({dev_id}): wifi_snr_db cannot be negative ({val})")
                except (ValueError, TypeError):
                    item_errors.append(f"Item #{idx} ({dev_id}): wifi_snr_db must be numeric")

            if item_errors:
                validation_errors.extend(item_errors)
            else:
                valid_records.append(item)

        return valid_records, validation_errors
