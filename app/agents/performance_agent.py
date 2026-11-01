from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from agents.base_agent import BaseAgent
from communication.models import (
    AgentMessage,
    AgentStatus,
    EvidenceItem,
    Finding,
    Severity,
)
from communication.protocol import create_agent_message, create_error_message

logger = logging.getLogger("agent.performance_agent")


class PerformanceSeverity(str, Enum):
    NORMAL = "normal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PerformanceStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    INSUFFICIENT_DATA = "insufficient_data"


class PerformanceThresholds(BaseModel):
    """
    Configurable performance thresholds for network anomaly detection.
    Can be instantiated with custom values without modifying agent source code.
    """
    model_config = ConfigDict(populate_by_name=True)

    # Latency (ms)
    latency_normal_max_ms: float = Field(default=50.0, description="Upper bound for normal latency")
    latency_critical_ms: float = Field(default=150.0, description="Threshold for critical latency")

    # Jitter (ms)
    jitter_normal_max_ms: float = Field(default=20.0, description="Upper bound for normal jitter")
    jitter_critical_ms: float = Field(default=50.0, description="Threshold for critical jitter")

    # Packet Loss (%)
    packet_loss_normal_max_pct: float = Field(default=1.0, description="Upper bound for normal loss")
    packet_loss_critical_pct: float = Field(default=5.0, description="Threshold for critical packet loss")

    # Bandwidth Utilization (%)
    bandwidth_normal_max_pct: float = Field(default=70.0, description="Upper bound for normal bandwidth")
    bandwidth_critical_pct: float = Field(default=90.0, description="Threshold for critical saturation")

    # Expected Throughput (Mbps, optional baseline)
    expected_throughput_mbps: Optional[float] = Field(default=None, description="Expected operational throughput baseline")
    low_throughput_ratio_threshold: float = Field(
        default=0.30,
        description="Fraction of expected throughput below which throughput is considered unusually low",
    )


class PerformanceFinding(BaseModel):
    """
    Structured performance anomaly finding with evidence and causal implications.
    Complies with Milestone 3 requirements and interoperates with global Finding models.
    """
    model_config = ConfigDict(populate_by_name=True)

    finding_id: str = Field(default_factory=lambda: f"FND-PERF-{uuid.uuid4().hex[:6].upper()}")
    metric_name: str = Field(..., description="Name of the analyzed metric")
    observed_value: Any = Field(..., description="Value or statistical aggregate observed")
    expected_range: str = Field(..., description="Configured normal threshold or baseline range")
    severity: str = Field(..., description="Severity level: normal, low, medium, high, critical")
    evidence_description: str = Field(..., description="Detailed factual evidence description")
    probable_implication: str = Field(..., description="Impact on applications, protocols, and network behavior")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence in this finding")
    device_id: Optional[str] = Field(default=None, description="Associated device identifier")

    # Compatibility fields for global Finding schema
    category: str = Field(default="PERFORMANCE")
    title: str = Field(default="")
    description: str = Field(default="")
    affected_devices: List[str] = Field(default_factory=list)
    metrics: Dict[str, Any] = Field(default_factory=dict)

    def model_post_init(self, __context: Any) -> None:
        if not self.title:
            dev_str = f" on {self.device_id}" if self.device_id else ""
            self.title = f"[{self.severity.upper()}] {self.metric_name} Anomaly{dev_str}"
        if not self.description:
            self.description = f"{self.evidence_description} Implication: {self.probable_implication}"
        if self.device_id and not self.affected_devices:
            self.affected_devices = [self.device_id]


class PerformanceAgentResponse(BaseModel):
    """
    Structured output response for the Performance Monitoring Agent.
    Contains both Milestone 3 specific fields and global agent interoperability fields.
    """
    model_config = ConfigDict(populate_by_name=True)

    agent_id: str = Field(default="performance_agent")
    task_id: str = Field(...)
    execution_status: str = Field(default="SUCCESS", description="SUCCESS, WARNING, ERROR, INSUFFICIENT_DATA")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    analyzed_device_ids: List[str] = Field(default_factory=list)
    findings: List[PerformanceFinding] = Field(default_factory=list)
    overall_performance_status: str = Field(
        default="healthy",
        description="Overall performance assessment: healthy, degraded, critical, insufficient_data",
    )
    summary: str = Field(default="")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    errors: List[str] = Field(default_factory=list)

    # Global AgentMessage compatibility fields
    status: AgentStatus = Field(default=AgentStatus.SUCCESS)
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    evidence: List[EvidenceItem] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_agent_message(self) -> AgentMessage:
        """Adapts response to the global AgentMessage model."""
        global_findings: List[Finding] = []
        for pf in self.findings:
            sev_map = {
                "normal": Severity.INFO,
                "low": Severity.LOW,
                "medium": Severity.MEDIUM,
                "high": Severity.HIGH,
                "critical": Severity.CRITICAL,
            }
            global_sev = sev_map.get(pf.severity.lower(), Severity.MEDIUM)
            global_findings.append(
                Finding(
                    finding_id=pf.finding_id,
                    category="PERFORMANCE",
                    title=pf.title,
                    description=pf.description,
                    severity=global_sev,
                    affected_devices=pf.affected_devices,
                    metrics=pf.metrics or {"observed_value": pf.observed_value},
                )
            )

        return AgentMessage(
            message_id=self.message_id,
            task_id=self.task_id,
            agent_id=self.agent_id,
            timestamp=self.timestamp,
            status=self.status,
            findings=global_findings,
            evidence=self.evidence,
            confidence=self.confidence,
            errors=self.errors,
            metadata={
                **self.metadata,
                "overall_performance_status": self.overall_performance_status,
                "analyzed_device_ids": self.analyzed_device_ids,
                "summary": self.summary,
            },
        )


class PerformanceAgent(BaseAgent):
    """
    Specialized Performance Monitoring Agent.
    Analyzes telemetry records across multiple network devices, detects multi-dimensional
    performance anomalies against configurable thresholds, and formulates evidence-based findings.
    """

    def __init__(self, thresholds: Optional[PerformanceThresholds] = None):
        super().__init__(
            agent_id="performance_agent",
            name="Network Performance Specialist",
            description="Analyzes transmission delay, packet loss, jitter variations, and throughput bottlenecks.",
        )
        self.thresholds = thresholds or PerformanceThresholds()

    def execute(
        self,
        task_id: str,
        telemetry: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> PerformanceAgentResponse:
        """
        Executes diagnostic analysis on provided telemetry dataset.
        Guarantees a PerformanceAgentResponse return with safe error handling.
        """
        start_time = time.perf_counter()
        context = context or {}

        try:
            valid_records, validation_errors = self._normalize_and_validate(telemetry)
            if not valid_records:
                exec_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return PerformanceAgentResponse(
                    agent_id=self.agent_id,
                    task_id=task_id,
                    execution_status="INSUFFICIENT_DATA",
                    status=AgentStatus.INSUFFICIENT_DATA,
                    timestamp=datetime.now(timezone.utc),
                    analyzed_device_ids=[],
                    findings=[
                        PerformanceFinding(
                            metric_name="dataset",
                            observed_value=0,
                            expected_range=">= 1 record",
                            severity=PerformanceSeverity.LOW.value,
                            evidence_description="No valid performance metric records available for evaluation.",
                            probable_implication="Performance health cannot be evaluated without valid metric samples.",
                            confidence_score=0.0,
                        )
                    ],
                    overall_performance_status=PerformanceStatus.INSUFFICIENT_DATA.value,
                    summary="Telemetry dataset is empty or contains no valid performance records.",
                    confidence=0.0,
                    errors=[str(e) for e in validation_errors],
                    metadata={"execution_time_ms": exec_time_ms, "record_count": 0},
                )

            df = pd.DataFrame(valid_records)

            # Calls analyze() so any subclass or monkeypatch is respected
            findings, evidence, confidence, errors = self.analyze(df, context)

            if validation_errors:
                errors.extend([str(e) for e in validation_errors])

            analyzed_devices = df["device_id"].unique().tolist() if "device_id" in df.columns else ["unknown"]
            has_critical = any(f.severity.lower() == "critical" for f in findings)
            has_warning = any(f.severity.lower() in ["high", "medium"] for f in findings)

            if has_critical:
                overall_status = PerformanceStatus.CRITICAL.value
            elif has_warning:
                overall_status = PerformanceStatus.DEGRADED.value
            else:
                overall_status = PerformanceStatus.HEALTHY.value

            exec_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            summary = self._formulate_summary(overall_status, findings, analyzed_devices, len(df))

            status_enum = AgentStatus.SUCCESS
            if errors and not findings:
                status_enum = AgentStatus.WARNING
            elif errors and overall_status == PerformanceStatus.CRITICAL.value:
                status_enum = AgentStatus.ERROR

            return PerformanceAgentResponse(
                agent_id=self.agent_id,
                task_id=task_id,
                execution_status="SUCCESS" if not errors else "WARNING",
                status=status_enum,
                timestamp=datetime.now(timezone.utc),
                analyzed_device_ids=analyzed_devices,
                findings=findings,
                overall_performance_status=overall_status,
                summary=summary,
                confidence=confidence,
                errors=errors,
                evidence=evidence,
                metadata={
                    "execution_time_ms": exec_time_ms,
                    "record_count": len(df),
                    "agent_name": self.name,
                },
            )

        except Exception as exc:
            self.logger.exception(f"Unhandled exception in agent {self.agent_id}: {exc}")
            exec_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            return PerformanceAgentResponse(
                agent_id=self.agent_id,
                task_id=task_id,
                execution_status="ERROR",
                status=AgentStatus.ERROR,
                timestamp=datetime.now(timezone.utc),
                analyzed_device_ids=[],
                findings=[],
                overall_performance_status=PerformanceStatus.INSUFFICIENT_DATA.value,
                summary=f"Agent runtime failure: {str(exc)}",
                confidence=0.0,
                errors=[f"Agent runtime error: {str(exc)}"],
                metadata={"execution_time_ms": exec_time_ms},
            )

    def analyze(
        self,
        df: pd.DataFrame,
        context: Dict[str, Any],
    ) -> Tuple[List[PerformanceFinding], List[EvidenceItem], float, List[str]]:
        """
        Core domain analysis on DataFrame.
        Evaluates metrics per device and across the entire dataset against configured thresholds.
        """
        findings: List[PerformanceFinding] = []
        evidence_items: List[EvidenceItem] = []
        errors: List[str] = []

        active_thresholds = context.get("thresholds", self.thresholds) if context else self.thresholds
        analyzed_devices = df["device_id"].unique().tolist() if "device_id" in df.columns else ["unknown"]

        device_groups = df.groupby("device_id") if "device_id" in df.columns and len(analyzed_devices) > 1 else [(None, df)]

        for dev_id, dev_df in device_groups:
            self._analyze_latency(dev_df, dev_id, active_thresholds, findings, evidence_items)
            self._analyze_jitter(dev_df, dev_id, active_thresholds, findings, evidence_items)
            self._analyze_packet_loss(dev_df, dev_id, active_thresholds, findings, evidence_items)
            self._analyze_bandwidth(dev_df, dev_id, active_thresholds, findings, evidence_items)
            self._analyze_throughput(dev_df, dev_id, active_thresholds, findings, evidence_items)

        # Compute confidence
        if not findings:
            confidence = 0.95 if len(df) >= 5 else 0.70
            findings.append(
                PerformanceFinding(
                    metric_name="performance_overall",
                    observed_value="nominal",
                    expected_range=f"Latency <= {active_thresholds.latency_normal_max_ms}ms, Loss <= {active_thresholds.packet_loss_normal_max_pct}%, Bandwidth <= {active_thresholds.bandwidth_normal_max_pct}%",
                    severity=PerformanceSeverity.NORMAL.value,
                    title="Nominal Network Performance",
                    evidence_description=f"All transmission metrics across {len(analyzed_devices)} device(s) are within healthy operational thresholds.",
                    probable_implication="Network transport layer is healthy; no queuing or transmission bottlenecks.",
                    confidence_score=confidence,
                    affected_devices=analyzed_devices,
                    metrics={"evaluated_records": len(df)},
                )
            )
        else:
            finding_confidences = [f.confidence_score for f in findings]
            avg_conf = float(np.mean(finding_confidences)) if finding_confidences else 0.80
            sample_boost = 0.05 if len(df) >= 10 else 0.0
            confidence = min(0.98, max(0.60, round(avg_conf + sample_boost, 2)))

        return findings, evidence_items, confidence, errors

    def analyze_telemetry(
        self,
        telemetry: Any,
        task_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        thresholds: Optional[PerformanceThresholds] = None,
    ) -> PerformanceAgentResponse:
        """
        Direct Milestone 3 analysis interface with optional override thresholds.
        """
        ctx = dict(context or {})
        if thresholds:
            ctx["thresholds"] = thresholds
        t_id = task_id or f"TASK-{uuid.uuid4().hex[:8].upper()}"
        return self.execute(t_id, telemetry, context=ctx)

    # -------------------------------------------------------------------------
    # DOMAIN METRIC DETECTORS
    # -------------------------------------------------------------------------

    def _analyze_latency(
        self,
        df: pd.DataFrame,
        device_id: Optional[str],
        th: PerformanceThresholds,
        findings: List[PerformanceFinding],
        evidence_items: List[EvidenceItem],
    ) -> None:
        if "latency_ms" not in df.columns or not df["latency_ms"].notna().any():
            return

        valid = df["latency_ms"].dropna()
        max_lat = float(valid.max())
        mean_lat = float(valid.mean())
        p95_lat = float(np.percentile(valid, 95))

        dev_label = f"Device '{device_id}': " if device_id else ""

        if max_lat > th.latency_critical_ms or mean_lat > th.latency_normal_max_ms:
            is_critical = max_lat > th.latency_critical_ms or mean_lat > th.latency_critical_ms
            sev = PerformanceSeverity.CRITICAL.value if is_critical else PerformanceSeverity.HIGH.value

            evidence = (
                f"{dev_label}Round-trip latency elevated to peak {max_lat:.1f}ms "
                f"(mean: {mean_lat:.1f}ms, 95th percentile: {p95_lat:.1f}ms), "
                f"exceeding normal threshold of {th.latency_normal_max_ms}ms."
            )
            implication = (
                "Severe transmission delay leads to TCP window throttling, application timeout risk, "
                "and interactive session lag."
            )
            dev_str = f" on {device_id}" if device_id else ""
            findings.append(
                PerformanceFinding(
                    metric_name="latency_ms",
                    observed_value=round(max_lat, 1),
                    expected_range=f"<= {th.latency_normal_max_ms} ms",
                    severity=sev,
                    title=f"Excessive Latency (RTT Degradation){dev_str}",
                    evidence_description=evidence,
                    probable_implication=implication,
                    confidence_score=0.92 if len(valid) >= 5 else 0.78,
                    device_id=device_id,
                    metrics={"mean_latency_ms": round(mean_lat, 1), "max_latency_ms": round(max_lat, 1), "p95_latency_ms": round(p95_lat, 1)},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="latency_ms",
                    observed_value=round(max_lat, 1),
                    threshold=th.latency_normal_max_ms,
                    unit="ms",
                    device_id=device_id,
                    details=evidence,
                )
            )
        elif max_lat > th.latency_normal_max_ms:
            evidence = (
                f"{dev_label}Latency reached peak {max_lat:.1f}ms (mean: {mean_lat:.1f}ms), "
                f"moderately breaching warning threshold {th.latency_normal_max_ms}ms."
            )
            dev_str = f" on {device_id}" if device_id else ""
            findings.append(
                PerformanceFinding(
                    metric_name="latency_ms",
                    observed_value=round(max_lat, 1),
                    expected_range=f"<= {th.latency_normal_max_ms} ms",
                    severity=PerformanceSeverity.MEDIUM.value,
                    title=f"Elevated Latency{dev_str}",
                    evidence_description=evidence,
                    probable_implication="Slight delay noticeable in interactive VoIP, gaming, or high-frequency RPC calls.",
                    confidence_score=0.85,
                    device_id=device_id,
                    metrics={"mean_latency_ms": round(mean_lat, 1), "max_latency_ms": round(max_lat, 1)},
                )
            )

    def _analyze_jitter(
        self,
        df: pd.DataFrame,
        device_id: Optional[str],
        th: PerformanceThresholds,
        findings: List[PerformanceFinding],
        evidence_items: List[EvidenceItem],
    ) -> None:
        if "jitter_ms" not in df.columns or not df["jitter_ms"].notna().any():
            return

        valid = df["jitter_ms"].dropna()
        max_jit = float(valid.max())
        mean_jit = float(valid.mean())
        dev_label = f"Device '{device_id}': " if device_id else ""

        if max_jit > th.jitter_critical_ms or max_jit > th.jitter_normal_max_ms:
            sev = PerformanceSeverity.CRITICAL.value if max_jit > th.jitter_critical_ms else PerformanceSeverity.HIGH.value
            evidence = f"{dev_label}Peak jitter reached {max_jit:.2f}ms (mean: {mean_jit:.2f}ms), exceeding normal threshold {th.jitter_normal_max_ms}ms."
            implication = "Severe delay variation results in packet reordering, buffer under-runs, and choppy real-time audio/video calls."
            dev_str = f" on {device_id}" if device_id else ""
            findings.append(
                PerformanceFinding(
                    metric_name="jitter_ms",
                    observed_value=round(max_jit, 2),
                    expected_range=f"<= {th.jitter_normal_max_ms} ms",
                    severity=sev,
                    title=f"Elevated Transmission Jitter{dev_str}",
                    evidence_description=evidence,
                    probable_implication=implication,
                    confidence_score=0.90 if max_jit > th.jitter_critical_ms else 0.82,
                    device_id=device_id,
                    metrics={"max_jitter_ms": round(max_jit, 2), "mean_jitter_ms": round(mean_jit, 2)},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="jitter_ms",
                    observed_value=round(max_jit, 2),
                    threshold=th.jitter_normal_max_ms,
                    unit="ms",
                    device_id=device_id,
                    details=evidence,
                )
            )

    def _analyze_packet_loss(
        self,
        df: pd.DataFrame,
        device_id: Optional[str],
        th: PerformanceThresholds,
        findings: List[PerformanceFinding],
        evidence_items: List[EvidenceItem],
    ) -> None:
        loss_col = "packet_loss_percent" if "packet_loss_percent" in df.columns else ("packet_loss_pct" if "packet_loss_pct" in df.columns else None)
        if not loss_col or not df[loss_col].notna().any():
            return

        valid = df[loss_col].dropna()
        max_loss = float(valid.max())
        mean_loss = float(valid.mean())
        dev_label = f"Device '{device_id}': " if device_id else ""

        if max_loss > th.packet_loss_critical_pct or mean_loss > th.packet_loss_normal_max_pct:
            is_critical = max_loss > th.packet_loss_critical_pct or mean_loss > th.packet_loss_critical_pct
            sev = PerformanceSeverity.CRITICAL.value if is_critical else PerformanceSeverity.HIGH.value
            evidence = f"{dev_label}Significant packet loss detected peaking at {max_loss:.2f}% (mean: {mean_loss:.2f}%), exceeding normal threshold {th.packet_loss_normal_max_pct}%."
            implication = "TCP retransmission cascades, throughput collapse, and dropped application connections."
            dev_str = f" on {device_id}" if device_id else ""
            findings.append(
                PerformanceFinding(
                    metric_name="packet_loss_percent",
                    observed_value=round(max_loss, 2),
                    expected_range=f"<= {th.packet_loss_normal_max_pct} %",
                    severity=sev,
                    title=f"Significant Packet Loss Detected{dev_str}",
                    evidence_description=evidence,
                    probable_implication=implication,
                    confidence_score=0.94 if len(valid) >= 5 else 0.80,
                    device_id=device_id,
                    metrics={"max_loss_pct": round(max_loss, 2), "mean_loss_pct": round(mean_loss, 2)},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="packet_loss_percent",
                    observed_value=round(max_loss, 2),
                    threshold=th.packet_loss_normal_max_pct,
                    unit="%",
                    device_id=device_id,
                    details=evidence,
                )
            )
        elif max_loss > th.packet_loss_normal_max_pct:
            evidence = f"{dev_label}Intermittent packet loss of {max_loss:.2f}% observed, exceeding {th.packet_loss_normal_max_pct}%."
            dev_str = f" on {device_id}" if device_id else ""
            findings.append(
                PerformanceFinding(
                    metric_name="packet_loss_percent",
                    observed_value=round(max_loss, 2),
                    expected_range=f"<= {th.packet_loss_normal_max_pct} %",
                    severity=PerformanceSeverity.MEDIUM.value,
                    title=f"Intermittent Packet Loss{dev_str}",
                    evidence_description=evidence,
                    probable_implication="Occasional TCP retransmissions causing momentary latency spikes.",
                    confidence_score=0.82,
                    device_id=device_id,
                    metrics={"max_loss_pct": round(max_loss, 2)},
                )
            )

    def _analyze_bandwidth(
        self,
        df: pd.DataFrame,
        device_id: Optional[str],
        th: PerformanceThresholds,
        findings: List[PerformanceFinding],
        evidence_items: List[EvidenceItem],
    ) -> None:
        bw_col = "bandwidth_utilization_percent" if "bandwidth_utilization_percent" in df.columns else ("bandwidth_util_pct" if "bandwidth_util_pct" in df.columns else None)
        if not bw_col or not df[bw_col].notna().any():
            return

        valid = df[bw_col].dropna()
        max_bw = float(valid.max())
        mean_bw = float(valid.mean())
        dev_label = f"Device '{device_id}': " if device_id else ""

        if max_bw > th.bandwidth_critical_pct or max_bw > th.bandwidth_normal_max_pct:
            sev = PerformanceSeverity.CRITICAL.value if max_bw > th.bandwidth_critical_pct else PerformanceSeverity.HIGH.value
            evidence = f"{dev_label}Bandwidth utilization reached saturation at {max_bw:.1f}% (mean: {mean_bw:.1f}%), exceeding threshold {th.bandwidth_normal_max_pct}%."
            implication = "Exhausted interface capacity causing buffer queuing, high latency, tail drops, and packet discards."
            dev_str = f" on {device_id}" if device_id else ""
            findings.append(
                PerformanceFinding(
                    metric_name="bandwidth_utilization_percent",
                    observed_value=round(max_bw, 1),
                    expected_range=f"<= {th.bandwidth_normal_max_pct} %",
                    severity=sev,
                    title=f"Link Bandwidth Saturation{dev_str}",
                    evidence_description=evidence,
                    probable_implication=implication,
                    confidence_score=0.95 if max_bw > th.bandwidth_critical_pct else 0.85,
                    device_id=device_id,
                    metrics={"max_bw_pct": round(max_bw, 1), "mean_bw_pct": round(mean_bw, 1)},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="bandwidth_utilization_percent",
                    observed_value=round(max_bw, 1),
                    threshold=th.bandwidth_normal_max_pct,
                    unit="%",
                    device_id=device_id,
                    details=evidence,
                )
            )

    def _analyze_throughput(
        self,
        df: pd.DataFrame,
        device_id: Optional[str],
        th: PerformanceThresholds,
        findings: List[PerformanceFinding],
        evidence_items: List[EvidenceItem],
    ) -> None:
        if "throughput_mbps" not in df.columns or not df["throughput_mbps"].notna().any():
            return

        if th.expected_throughput_mbps is None or th.expected_throughput_mbps <= 0:
            return

        valid = df["throughput_mbps"].dropna()
        mean_tp = float(valid.mean())
        min_tp = float(valid.min())
        dev_label = f"Device '{device_id}': " if device_id else ""

        low_threshold = th.expected_throughput_mbps * th.low_throughput_ratio_threshold

        if min_tp < low_threshold or mean_tp < low_threshold:
            evidence = (
                f"{dev_label}Throughput fell to minimum {min_tp:.1f} Mbps (mean: {mean_tp:.1f} Mbps), "
                f"which is significantly below the expected baseline of {th.expected_throughput_mbps:.1f} Mbps "
                f"(threshold: < {low_threshold:.1f} Mbps)."
            )
            implication = (
                "Unusually low throughput observed. Note: Low throughput alone does not prove a network fault "
                "(could indicate an idle link or absence of active transfers), but warrants correlation with packet loss and link state."
            )
            dev_str = f" on {device_id}" if device_id else ""
            findings.append(
                PerformanceFinding(
                    metric_name="throughput_mbps",
                    observed_value=round(min_tp, 1),
                    expected_range=f">= {low_threshold:.1f} Mbps (baseline: {th.expected_throughput_mbps} Mbps)",
                    severity=PerformanceSeverity.LOW.value,
                    title=f"Unusually Low Throughput Detected{dev_str}",
                    evidence_description=evidence,
                    probable_implication=implication,
                    confidence_score=0.72,
                    device_id=device_id,
                    metrics={"min_throughput_mbps": round(min_tp, 1), "expected_baseline_mbps": th.expected_throughput_mbps},
                )
            )

    def _formulate_summary(
        self,
        overall_status: str,
        findings: List[PerformanceFinding],
        devices: List[str],
        record_count: int,
    ) -> str:
        dev_count = len(devices)
        if overall_status == PerformanceStatus.HEALTHY.value:
            return f"Network performance is healthy across {dev_count} device(s) ({record_count} records evaluated). All metrics within SLA."

        anomalies = [f"{f.metric_name} ({f.severity})" for f in findings]
        return (
            f"Performance assessment: {overall_status.upper()}. "
            f"Detected {len(findings)} anomaly/anomalies across {dev_count} device(s): {', '.join(anomalies)}. "
            f"Evaluated {record_count} telemetry samples."
        )

    # -------------------------------------------------------------------------
    # INPUT NORMALIZATION
    # -------------------------------------------------------------------------

    def _normalize_and_validate(self, telemetry: Any) -> Tuple[List[Dict[str, Any]], List[Any]]:
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
        validation_errors: List[Any] = []

        for idx, item in enumerate(raw_items):
            if not isinstance(item, dict):
                validation_errors.append(f"Item #{idx}: Expected dict, got {type(item).__name__}")
                continue

            dev_id = item.get("device_id")
            if not dev_id or not str(dev_id).strip():
                validation_errors.append(f"Item #{idx}: Missing required 'device_id'")
                continue

            item_errors = []
            for metric in ["latency_ms", "jitter_ms", "throughput_mbps"]:
                if metric in item and item[metric] is not None:
                    try:
                        val = float(item[metric])
                        if val < 0.0:
                            item_errors.append(f"Item #{idx}: {metric} cannot be negative ({val})")
                    except (ValueError, TypeError):
                        item_errors.append(f"Item #{idx}: {metric} must be numeric")

            loss_key = "packet_loss_percent" if "packet_loss_percent" in item else "packet_loss_pct"
            if loss_key in item and item[loss_key] is not None:
                try:
                    val = float(item[loss_key])
                    if val < 0.0 or val > 100.0:
                        item_errors.append(f"Item #{idx}: packet loss must be in 0-100% ({val})")
                except (ValueError, TypeError):
                    item_errors.append(f"Item #{idx}: packet loss must be numeric")

            bw_key = "bandwidth_utilization_percent" if "bandwidth_utilization_percent" in item else "bandwidth_util_pct"
            if bw_key in item and item[bw_key] is not None:
                try:
                    val = float(item[bw_key])
                    if val < 0.0 or val > 100.0:
                        item_errors.append(f"Item #{idx}: bandwidth utilization must be in 0-100% ({val})")
                except (ValueError, TypeError):
                    item_errors.append(f"Item #{idx}: bandwidth utilization must be numeric")

            if item_errors:
                validation_errors.extend(item_errors)
            else:
                valid_records.append(item)

        return valid_records, validation_errors
