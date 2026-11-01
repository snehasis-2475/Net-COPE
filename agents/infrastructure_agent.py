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

logger = logging.getLogger("agent.infrastructure_agent")


class InfrastructureSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class InfrastructureStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    INSUFFICIENT_DATA = "insufficient_data"


class InfrastructureThresholds(BaseModel):
    """
    Configurable infrastructure health thresholds for hardware, resource, and interface evaluation.
    Can be configured at initialization without modifying the agent's source code.
    """
    model_config = ConfigDict(populate_by_name=True)

    # CPU Utilization (%)
    cpu_warn_pct: float = Field(default=70.0, ge=0.0, le=100.0, description="Warning threshold for CPU utilization")
    cpu_crit_pct: float = Field(default=90.0, ge=0.0, le=100.0, description="Critical threshold for CPU utilization")

    # Memory Utilization (%)
    memory_warn_pct: float = Field(default=75.0, ge=0.0, le=100.0, description="Warning threshold for memory utilization")
    memory_crit_pct: float = Field(default=90.0, ge=0.0, le=100.0, description="Critical threshold for memory utilization")

    # Device Status Mappings
    device_status_online: List[str] = Field(
        default_factory=lambda: ["active", "online", "up", "healthy"],
        description="Status values treated as healthy online states",
    )
    device_status_warning: List[str] = Field(
        default_factory=lambda: ["degraded", "rebooting"],
        description="Status values indicating impaired or warning state",
    )
    device_status_critical: List[str] = Field(
        default_factory=lambda: ["offline", "down", "failed"],
        description="Status values indicating critical offline state",
    )

    # Interface Errors (Cumulative count)
    interface_errors_warn: int = Field(
        default=0,
        ge=0,
        description="Warning threshold: greater than this is warning (default: >0)",
    )
    interface_errors_crit: int = Field(
        default=20,
        ge=0,
        description="Critical threshold: greater than this is critical (default: >20)",
    )

    # Queue Drops (Count)
    queue_drops_warn: int = Field(
        default=0,
        ge=0,
        description="Warning threshold: greater than this is warning (default: >0)",
    )
    queue_drops_crit: int = Field(
        default=50,
        ge=0,
        description="Critical threshold: greater than this is critical (default: >50)",
    )

    # Device Availability (% if present)
    availability_warn_pct: float = Field(
        default=99.0,
        ge=0.0,
        le=100.0,
        description="Warning threshold: availability drops below this",
    )
    availability_crit_pct: float = Field(
        default=90.0,
        ge=0.0,
        le=100.0,
        description="Critical threshold: availability drops below or equal to this",
    )


class InfrastructureFinding(BaseModel):
    """
    Structured infrastructure health finding with evidence, diagnostic explanation, and probable impact.
    Strictly adheres to Milestone 4 requirements and provides interoperability with global Finding models.
    """
    model_config = ConfigDict(populate_by_name=True)

    finding_id: str = Field(default_factory=lambda: f"FND-INFRA-{uuid.uuid4().hex[:6].upper()}")
    agent_id: str = Field(default="infrastructure_agent")
    device_id: Optional[str] = Field(default=None, description="Identifier of the affected device")
    metric: str = Field(..., description="Name of the evaluated metric or composite symptom")
    observed_value: Any = Field(..., description="Observed metric value or state")
    threshold: Any = Field(..., description="Configured normal threshold or expected baseline")
    severity: str = Field(..., description="Severity level: info, warning, critical")
    evidence: str = Field(..., description="Factual evidence statement describing the observation")
    explanation: str = Field(..., description="Diagnostic reasoning explaining root cause mechanics")
    probable_impact: str = Field(..., description="Potential operational impact on device and network")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Compatibility fields for global Finding schema and correlation agent
    category: str = Field(default="INFRASTRUCTURE")
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


class InfrastructureAgentResponse(BaseModel):
    """
    Structured output response for the Infrastructure Health Agent.
    Contains Milestone 4 specific fields, per-device summaries, and communication protocol interoperability.
    """
    model_config = ConfigDict(populate_by_name=True)

    agent_id: str = Field(default="infrastructure_agent")
    task_id: str = Field(...)
    status: Union[AgentStatus, str] = Field(
        default=AgentStatus.SUCCESS,
        description="Execution status conforming to AgentStatus enum or string",
    )
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    analyzed_device_count: int = Field(default=0)
    findings: List[InfrastructureFinding] = Field(default_factory=list)
    device_summaries: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    overall_status: str = Field(
        default="healthy",
        description="Overall infrastructure status: healthy, degraded, critical, insufficient_data",
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
        for inf in self.findings:
            sev_str = inf.severity.lower()
            if sev_str == "critical":
                sev = Severity.CRITICAL
            elif sev_str == "warning":
                sev = Severity.HIGH
            else:
                sev = Severity.INFO

            global_findings.append(
                Finding(
                    finding_id=inf.finding_id,
                    category=inf.category or "INFRASTRUCTURE",
                    title=inf.title,
                    description=inf.description,
                    severity=sev,
                    affected_devices=inf.affected_devices,
                    metric_name=inf.metric,
                    observed_value=inf.observed_value,
                    threshold_value=inf.threshold,
                    source_agent=self.agent_id,
                    finding_type="OBSERVED_EVIDENCE",
                    timestamp=self.timestamp,
                    metrics={
                        "observed_value": inf.observed_value,
                        "threshold": str(inf.threshold),
                        "metric": inf.metric,
                        "confidence": inf.confidence,
                        **inf.metrics,
                    },
                )
            )

        status_enum = AgentStatus.SUCCESS
        if self.overall_status == InfrastructureStatus.INSUFFICIENT_DATA.value:
            status_enum = AgentStatus.INSUFFICIENT_DATA
        elif self.errors and not self.findings:
            status_enum = AgentStatus.ERROR
        elif self.errors:
            status_enum = AgentStatus.WARNING

        meta = dict(self.metadata)
        meta.update({
            "overall_infrastructure_status": self.overall_status,
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


class InfrastructureAgent(BaseAgent):
    """
    Upgraded, production-quality Infrastructure Health Agent.
    Analyzes compute utilization (CPU/RAM), operational state, interface errors,
    buffer tail drops, and physical link integrity.
    """

    def __init__(self, thresholds: Optional[InfrastructureThresholds] = None):
        super().__init__(
            agent_id="infrastructure_agent",
            name="Infrastructure Health Specialist",
            description="Analyzes network compute load (CPU/RAM), operational status, interface errors, and queue drops.",
        )
        self.thresholds = thresholds or InfrastructureThresholds()

    # -------------------------------------------------------------------------
    # MAIN AGENT EXECUTION INTERFACE
    # -------------------------------------------------------------------------

    def execute(
        self,
        task_id: str,
        telemetry: Union[pd.DataFrame, List[Any], Dict[str, Any]],
        context: Optional[Dict[str, Any]] = None,
    ) -> InfrastructureAgentResponse:
        """
        Executes end-to-end infrastructure diagnostics on telemetry input.
        Returns a structured InfrastructureAgentResponse that can be adapted to AgentMessage.
        """
        start_time = time.perf_counter()
        context = context or {}
        active_thresholds = context.get("thresholds", self.thresholds)

        valid_records, validation_errors = self._normalize_and_validate(telemetry)

        # Empty / completely invalid data handling
        if not valid_records:
            exec_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            errors = [str(e) for e in validation_errors] or ["No telemetry records provided for evaluation."]
            return InfrastructureAgentResponse(
                agent_id=self.agent_id,
                task_id=task_id,
                status=AgentStatus.INSUFFICIENT_DATA,
                timestamp=datetime.now(timezone.utc),
                analyzed_device_count=0,
                findings=[
                    InfrastructureFinding(
                        metric="infrastructure_telemetry",
                        observed_value=0,
                        threshold=">= 1 record",
                        severity=InfrastructureSeverity.INFO.value,
                        evidence="Telemetry dataset is empty or contains no valid infrastructure records.",
                        explanation="Infrastructure health cannot be evaluated without valid metric samples.",
                        probable_impact="Unable to assess hardware health or prevent resource exhaustion.",
                        confidence=0.0,
                        title="Empty or Invalid Infrastructure Telemetry",
                    )
                ],
                device_summaries={},
                overall_status=InfrastructureStatus.INSUFFICIENT_DATA.value,
                summary="Telemetry dataset is empty or contains no valid infrastructure records.",
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

        # Determine overall infrastructure status
        has_critical = any(f.severity.lower() == InfrastructureSeverity.CRITICAL.value for f in findings)
        has_warning = any(f.severity.lower() == InfrastructureSeverity.WARNING.value for f in findings)

        if has_critical:
            overall_status = InfrastructureStatus.CRITICAL.value
        elif has_warning:
            overall_status = InfrastructureStatus.DEGRADED.value
        else:
            overall_status = InfrastructureStatus.HEALTHY.value

        exec_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        summary = self._formulate_summary(overall_status, findings, analyzed_devices, len(df))

        status_enum = AgentStatus.SUCCESS
        if all_errors and not findings:
            status_enum = AgentStatus.ERROR
        elif all_errors:
            status_enum = AgentStatus.WARNING

        return InfrastructureAgentResponse(
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
        thresholds: Optional[InfrastructureThresholds] = None,
    ) -> InfrastructureAgentResponse:
        """Convenience direct invocation interface with optional threshold overrides."""
        ctx = dict(context or {})
        if thresholds:
            ctx["thresholds"] = thresholds
        t_id = task_id or f"TASK-INFRA-{uuid.uuid4().hex[:8].upper()}"
        return self.execute(t_id, telemetry, context=ctx)

    # -------------------------------------------------------------------------
    # CORE DOMAIN ANALYSIS (DataFrame -> Findings, Evidence, Confidence, Errors)
    # -------------------------------------------------------------------------

    def analyze(
        self,
        df: pd.DataFrame,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[InfrastructureFinding], List[EvidenceItem], float, List[str]]:
        """
        Analyzes normalized DataFrame per device against active thresholds.
        Evaluates CPU, RAM, device status, interface errors, queue drops, and correlates indicators.
        """
        context = context or {}
        active_thresholds = context.get("thresholds", self.thresholds)

        findings: List[InfrastructureFinding] = []
        evidence_items: List[EvidenceItem] = []
        errors: List[str] = []

        analyzed_devices = df["device_id"].unique().tolist() if "device_id" in df.columns else ["unknown"]
        device_groups = df.groupby("device_id") if "device_id" in df.columns and len(analyzed_devices) > 1 else [(analyzed_devices[0] if analyzed_devices else None, df)]

        for dev_id, dev_df in device_groups:
            # 1. Evaluate individual metrics
            cpu_val = self._analyze_cpu(dev_df, dev_id, active_thresholds, findings, evidence_items)
            mem_val = self._analyze_memory(dev_df, dev_id, active_thresholds, findings, evidence_items)
            status_val = self._analyze_device_status(dev_df, dev_id, active_thresholds, findings, evidence_items)
            errs_val = self._analyze_interface_errors(dev_df, dev_id, active_thresholds, findings, evidence_items)
            drops_val = self._analyze_queue_drops(dev_df, dev_id, active_thresholds, findings, evidence_items)
            self._analyze_device_availability(dev_df, dev_id, active_thresholds, findings, evidence_items)
            self._analyze_interface_status(dev_df, dev_id, active_thresholds, findings, evidence_items)

            # 2. Correlate indicators for this device
            self._correlate_device_indicators(
                dev_id=dev_id,
                cpu_peak=cpu_val,
                mem_peak=mem_val,
                status=status_val,
                errs_peak=errs_val,
                drops_peak=drops_val,
                th=active_thresholds,
                findings=findings,
                evidence_items=evidence_items,
            )

        # 3. Overall confidence calculation
        if not findings:
            confidence = 0.95 if len(df) >= 5 else 0.70
            findings.append(
                InfrastructureFinding(
                    metric="infrastructure_overall",
                    observed_value="healthy",
                    threshold="all operational limits",
                    severity=InfrastructureSeverity.INFO.value,
                    title="Healthy Infrastructure Status",
                    evidence=f"Compute load, memory headroom, device operational state, and queue buffers operating nominally across {len(analyzed_devices)} device(s).",
                    explanation="All hardware infrastructure metrics are well within safe thresholds.",
                    probable_impact="Hardware infrastructure is fully operational and forwarding traffic nominally.",
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

    def _analyze_cpu(
        self,
        df: pd.DataFrame,
        device_id: Optional[str],
        th: InfrastructureThresholds,
        findings: List[InfrastructureFinding],
        evidence_items: List[EvidenceItem],
    ) -> Optional[float]:
        col = "cpu_utilization_percent" if "cpu_utilization_percent" in df.columns else ("cpu_util_pct" if "cpu_util_pct" in df.columns else None)
        if not col or not df[col].notna().any():
            return None

        valid = df[col].dropna()
        max_cpu = float(valid.max())
        mean_cpu = float(valid.mean())
        dev_label = f"Device '{device_id}': " if device_id else ""
        dev_str = f" on {device_id}" if device_id else ""

        if max_cpu > th.cpu_crit_pct:
            evidence = f"{dev_label}CPU utilization peaked at {max_cpu:.1f}% (mean: {mean_cpu:.1f}%), exceeding critical threshold of {th.cpu_crit_pct}%."
            explanation = "Severe control plane CPU exhaustion causes packet processing delays, routing protocol packet drops, and high latency."
            impact = "Risk of control plane unresponsiveness, BGP/OSPF peer flapping, and dropped transit traffic."
            findings.append(
                InfrastructureFinding(
                    metric="cpu_utilization",
                    observed_value=round(max_cpu, 1),
                    threshold=f"<= {th.cpu_warn_pct}% (warn), <= {th.cpu_crit_pct}% (crit)",
                    severity=InfrastructureSeverity.CRITICAL.value,
                    title=f"Critical CPU Overload{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.94 if len(valid) >= 3 else 0.85,
                    device_id=device_id,
                    metrics={"max_cpu_pct": round(max_cpu, 1), "mean_cpu_pct": round(mean_cpu, 1)},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="cpu_util_pct",
                    observed_value=round(max_cpu, 1),
                    threshold=th.cpu_crit_pct,
                    unit="%",
                    device_id=device_id,
                    details=evidence,
                )
            )
        elif max_cpu > th.cpu_warn_pct:
            evidence = f"{dev_label}CPU utilization elevated to {max_cpu:.1f}% (mean: {mean_cpu:.1f}%), exceeding warning threshold of {th.cpu_warn_pct}%."
            explanation = "Elevated compute utilization reduces processing headroom for sudden traffic bursts."
            impact = "Potential queue buildup during traffic surges."
            findings.append(
                InfrastructureFinding(
                    metric="cpu_utilization",
                    observed_value=round(max_cpu, 1),
                    threshold=f"<= {th.cpu_warn_pct}%",
                    severity=InfrastructureSeverity.WARNING.value,
                    title=f"High CPU Warning{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.85,
                    device_id=device_id,
                    metrics={"max_cpu_pct": round(max_cpu, 1), "mean_cpu_pct": round(mean_cpu, 1)},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="cpu_util_pct",
                    observed_value=round(max_cpu, 1),
                    threshold=th.cpu_warn_pct,
                    unit="%",
                    device_id=device_id,
                    details=evidence,
                )
            )

        return max_cpu

    def _analyze_memory(
        self,
        df: pd.DataFrame,
        device_id: Optional[str],
        th: InfrastructureThresholds,
        findings: List[InfrastructureFinding],
        evidence_items: List[EvidenceItem],
    ) -> Optional[float]:
        col = "memory_utilization_percent" if "memory_utilization_percent" in df.columns else ("memory_util_pct" if "memory_util_pct" in df.columns else None)
        if not col or not df[col].notna().any():
            return None

        valid = df[col].dropna()
        max_mem = float(valid.max())
        mean_mem = float(valid.mean())
        dev_label = f"Device '{device_id}': " if device_id else ""
        dev_str = f" on {device_id}" if device_id else ""

        if max_mem > th.memory_crit_pct:
            evidence = f"{dev_label}RAM utilization peaked at {max_mem:.1f}% (mean: {mean_mem:.1f}%), exceeding critical threshold of {th.memory_crit_pct}%."
            explanation = "High risk of out-of-memory kernel panic, routing table allocation failure, or buffer starvation."
            impact = "Imminent crash, kernel OOM killer terminating routing daemons."
            findings.append(
                InfrastructureFinding(
                    metric="memory_utilization",
                    observed_value=round(max_mem, 1),
                    threshold=f"<= {th.memory_warn_pct}% (warn), <= {th.memory_crit_pct}% (crit)",
                    severity=InfrastructureSeverity.CRITICAL.value,
                    title=f"Memory Pressure / Leak Potential{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.92 if len(valid) >= 3 else 0.84,
                    device_id=device_id,
                    metrics={"max_memory_pct": round(max_mem, 1), "mean_memory_pct": round(mean_mem, 1)},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="memory_util_pct",
                    observed_value=round(max_mem, 1),
                    threshold=th.memory_crit_pct,
                    unit="%",
                    device_id=device_id,
                    details=evidence,
                )
            )
        elif max_mem > th.memory_warn_pct:
            evidence = f"{dev_label}RAM utilization reached {max_mem:.1f}% (mean: {mean_mem:.1f}%), exceeding warning threshold of {th.memory_warn_pct}%."
            explanation = "System memory operating with narrow headroom."
            impact = "Decreased buffer capacity and potential slowdown in dynamic table lookups."
            findings.append(
                InfrastructureFinding(
                    metric="memory_utilization",
                    observed_value=round(max_mem, 1),
                    threshold=f"<= {th.memory_warn_pct}%",
                    severity=InfrastructureSeverity.WARNING.value,
                    title=f"Elevated Memory Utilization{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.85,
                    device_id=device_id,
                    metrics={"max_memory_pct": round(max_mem, 1), "mean_memory_pct": round(mean_mem, 1)},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="memory_util_pct",
                    observed_value=round(max_mem, 1),
                    threshold=th.memory_warn_pct,
                    unit="%",
                    device_id=device_id,
                    details=evidence,
                )
            )

        return max_mem

    def _analyze_device_status(
        self,
        df: pd.DataFrame,
        device_id: Optional[str],
        th: InfrastructureThresholds,
        findings: List[InfrastructureFinding],
        evidence_items: List[EvidenceItem],
    ) -> Optional[str]:
        if "device_status" not in df.columns or not df["device_status"].notna().any():
            return None

        statuses = df["device_status"].dropna().astype(str).str.lower().unique().tolist()
        dev_label = f"Device '{device_id}': " if device_id else ""
        dev_str = f" on {device_id}" if device_id else ""

        crit_matches = [s for s in statuses if s in [x.lower() for x in th.device_status_critical]]
        warn_matches = [s for s in statuses if s in [x.lower() for x in th.device_status_warning]]

        if crit_matches:
            evidence = f"{dev_label}Device reported in critical offline state ({', '.join(crit_matches)})."
            explanation = "Node is completely unavailable or powered down, preventing packet forwarding."
            impact = "Total loss of connectivity for routes passing through this node."
            findings.append(
                InfrastructureFinding(
                    metric="device_status",
                    observed_value=", ".join(crit_matches),
                    threshold="online/active",
                    severity=InfrastructureSeverity.CRITICAL.value,
                    title=f"Device Offline / Critical Operational Outage{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.98,
                    device_id=device_id,
                    metrics={"reported_status": crit_matches},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="device_status",
                    observed_value=", ".join(crit_matches),
                    threshold="online",
                    device_id=device_id,
                    details=evidence,
                )
            )
            return crit_matches[0]
        elif warn_matches:
            evidence = f"{dev_label}Device reported in degraded/rebooting operational state ({', '.join(warn_matches)})."
            explanation = "Device operational health is impaired; sub-components or line cards may be malfunctioning or restarting."
            impact = "Reduced throughput, intermittent packet drop, and possible failover to alternate paths."
            findings.append(
                InfrastructureFinding(
                    metric="device_status",
                    observed_value=", ".join(warn_matches),
                    threshold="online/active",
                    severity=InfrastructureSeverity.WARNING.value,
                    title=f"Device Degraded Operational State{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.90,
                    device_id=device_id,
                    metrics={"reported_status": warn_matches},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="device_status",
                    observed_value=", ".join(warn_matches),
                    threshold="online",
                    device_id=device_id,
                    details=evidence,
                )
            )
            return warn_matches[0]

        return statuses[0] if statuses else None

    def _analyze_interface_errors(
        self,
        df: pd.DataFrame,
        device_id: Optional[str],
        th: InfrastructureThresholds,
        findings: List[InfrastructureFinding],
        evidence_items: List[EvidenceItem],
    ) -> Optional[int]:
        if "interface_errors" not in df.columns or not df["interface_errors"].notna().any():
            return None

        valid = df["interface_errors"].dropna()
        max_errs = int(valid.max())
        dev_label = f"Device '{device_id}': " if device_id else ""
        dev_str = f" on {device_id}" if device_id else ""

        # Note: Clearly identify metric as cumulative counter unless rate is available
        counter_note = "Interface error count is evaluated as a cumulative counter; rate of increase should be monitored across consecutive polls."

        if max_errs > th.interface_errors_crit:
            evidence = f"{dev_label}Accumulated {max_errs} interface CRC/frame errors, exceeding critical threshold of {th.interface_errors_crit}. {counter_note}"
            explanation = "Severe frame check sequence (FCS)/CRC errors typically indicate physical cabling degradation, dirty fiber optics, faulty SFP optics, or duplex mismatch."
            impact = "Corrupted Ethernet frames are dropped at MAC layer, forcing higher-layer TCP retransmissions and throughput degradation."
            findings.append(
                InfrastructureFinding(
                    metric="interface_errors",
                    observed_value=max_errs,
                    threshold=f"0 (healthy), <= {th.interface_errors_crit} (crit)",
                    severity=InfrastructureSeverity.CRITICAL.value,
                    title=f"Interface Frame / CRC Errors{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.93,
                    device_id=device_id,
                    metrics={"max_interface_errors": max_errs, "counter_type": "cumulative"},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="interface_errors",
                    observed_value=max_errs,
                    threshold=th.interface_errors_crit,
                    unit="errors (cumulative)",
                    device_id=device_id,
                    details=evidence,
                )
            )
        elif max_errs > th.interface_errors_warn:
            evidence = f"{dev_label}Accumulated {max_errs} interface CRC/frame errors, exceeding healthy baseline of {th.interface_errors_warn}. {counter_note}"
            explanation = "Intermittent framing errors detected on physical interface."
            impact = "Occasional packet retransmissions and minor link impairment."
            findings.append(
                InfrastructureFinding(
                    metric="interface_errors",
                    observed_value=max_errs,
                    threshold=f"0 (healthy)",
                    severity=InfrastructureSeverity.WARNING.value,
                    title=f"Interface CRC Errors Warning{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.85,
                    device_id=device_id,
                    metrics={"max_interface_errors": max_errs, "counter_type": "cumulative"},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="interface_errors",
                    observed_value=max_errs,
                    threshold=th.interface_errors_warn,
                    unit="errors (cumulative)",
                    device_id=device_id,
                    details=evidence,
                )
            )

        return max_errs

    def _analyze_queue_drops(
        self,
        df: pd.DataFrame,
        device_id: Optional[str],
        th: InfrastructureThresholds,
        findings: List[InfrastructureFinding],
        evidence_items: List[EvidenceItem],
    ) -> Optional[int]:
        if "queue_drops" not in df.columns or not df["queue_drops"].notna().any():
            return None

        valid = df["queue_drops"].dropna()
        max_drops = int(valid.max())
        dev_label = f"Device '{device_id}': " if device_id else ""
        dev_str = f" on {device_id}" if device_id else ""

        if max_drops > th.queue_drops_crit:
            evidence = f"{dev_label}Hardware packet buffer overflow resulted in {max_drops} queue tail-drops, breaching critical threshold {th.queue_drops_crit}."
            explanation = "Switch/router egress buffer space completely exhausted by burst traffic or line congestion, forcing packet discard."
            impact = "Severe packet drop inducing TCP backoff, connection throttling, and high retransmission rate."
            findings.append(
                InfrastructureFinding(
                    metric="queue_drops",
                    observed_value=max_drops,
                    threshold=f"0 (healthy), <= {th.queue_drops_crit} (crit)",
                    severity=InfrastructureSeverity.CRITICAL.value,
                    title=f"Hardware Queue Drops Detected{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.92,
                    device_id=device_id,
                    metrics={"max_queue_drops": max_drops},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="queue_drops",
                    observed_value=max_drops,
                    threshold=th.queue_drops_crit,
                    unit="drops",
                    device_id=device_id,
                    details=evidence,
                )
            )
        elif max_drops > th.queue_drops_warn:
            evidence = f"{dev_label}Observed {max_drops} dropped packets due to momentary hardware buffer saturation, exceeding baseline 0."
            explanation = "Occasional buffer tail-drops during bursty traffic intervals."
            impact = "Momentary throughput dips."
            findings.append(
                InfrastructureFinding(
                    metric="queue_drops",
                    observed_value=max_drops,
                    threshold="0",
                    severity=InfrastructureSeverity.WARNING.value,
                    title=f"Hardware Buffer Queue Drops Warning{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.84,
                    device_id=device_id,
                    metrics={"max_queue_drops": max_drops},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="queue_drops",
                    observed_value=max_drops,
                    threshold=th.queue_drops_warn,
                    unit="drops",
                    device_id=device_id,
                    details=evidence,
                )
            )

        return max_drops

    def _analyze_device_availability(
        self,
        df: pd.DataFrame,
        device_id: Optional[str],
        th: InfrastructureThresholds,
        findings: List[InfrastructureFinding],
        evidence_items: List[EvidenceItem],
    ) -> Optional[float]:
        if "device_availability" not in df.columns or not df["device_availability"].notna().any():
            return None

        valid = df["device_availability"].dropna()
        min_avail = float(valid.min())
        mean_avail = float(valid.mean())
        dev_label = f"Device '{device_id}': " if device_id else ""
        dev_str = f" on {device_id}" if device_id else ""

        if min_avail <= th.availability_crit_pct:
            evidence = f"{dev_label}Device availability dropped to {min_avail:.1f}% (mean: {mean_avail:.1f}%), breaching critical threshold {th.availability_crit_pct}%."
            explanation = "Heartbeat ping or ICMP probe failures indicate severe node unreachability or reboot cycles."
            impact = "Network outages and unreachable subnets."
            findings.append(
                InfrastructureFinding(
                    metric="device_availability",
                    observed_value=round(min_avail, 1),
                    threshold=f">= {th.availability_warn_pct}%",
                    severity=InfrastructureSeverity.CRITICAL.value,
                    title=f"Device Availability Outage / Impairment{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.95,
                    device_id=device_id,
                    metrics={"min_availability_pct": round(min_avail, 1), "mean_availability_pct": round(mean_avail, 1)},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="device_availability",
                    observed_value=round(min_avail, 1),
                    threshold=th.availability_crit_pct,
                    unit="%",
                    device_id=device_id,
                    details=evidence,
                )
            )
        elif min_avail < th.availability_warn_pct:
            evidence = f"{dev_label}Device availability degraded to {min_avail:.1f}% (mean: {mean_avail:.1f}%), below SLA {th.availability_warn_pct}%."
            explanation = "Intermittent reachability drops or delayed ICMP probe responses."
            impact = "Minor packet loss and management unresponsiveness."
            findings.append(
                InfrastructureFinding(
                    metric="device_availability",
                    observed_value=round(min_avail, 1),
                    threshold=f">= {th.availability_warn_pct}%",
                    severity=InfrastructureSeverity.WARNING.value,
                    title=f"Device Availability Warning{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.88,
                    device_id=device_id,
                    metrics={"min_availability_pct": round(min_avail, 1)},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="device_availability",
                    observed_value=round(min_avail, 1),
                    threshold=th.availability_warn_pct,
                    unit="%",
                    device_id=device_id,
                    details=evidence,
                )
            )

        return min_avail

    def _analyze_interface_status(
        self,
        df: pd.DataFrame,
        device_id: Optional[str],
        th: InfrastructureThresholds,
        findings: List[InfrastructureFinding],
        evidence_items: List[EvidenceItem],
    ) -> None:
        if "interface_status" not in df.columns or not df["interface_status"].notna().any():
            return

        abnormal = df[df["interface_status"].astype(str).str.lower().isin(["down", "flapping", "errdisable", "disabled"])]
        if not abnormal.empty:
            states = abnormal["interface_status"].astype(str).str.lower().unique().tolist()
            dev_label = f"Device '{device_id}': " if device_id else ""
            dev_str = f" on {device_id}" if device_id else ""
            is_down = "down" in states or "errdisable" in states
            severity = InfrastructureSeverity.CRITICAL.value if is_down else InfrastructureSeverity.WARNING.value

            evidence = f"{dev_label}Physical interface reported abnormal states ({', '.join(states)})."
            explanation = "Physical link layer is non-operational or repeatedly cycling link states."
            impact = "Traffic cannot traverse port; routing convergence or STP recalculation triggered."

            findings.append(
                InfrastructureFinding(
                    metric="interface_status",
                    observed_value=", ".join(states),
                    threshold="up",
                    severity=severity,
                    title=f"Interface Physical / Link Failure{dev_str}",
                    evidence=evidence,
                    explanation=explanation,
                    probable_impact=impact,
                    confidence=0.95,
                    device_id=device_id,
                    metrics={"abnormal_states": states},
                )
            )
            evidence_items.append(
                EvidenceItem(
                    metric_name="interface_status",
                    observed_value=", ".join(states),
                    threshold="up",
                    device_id=device_id,
                    details=evidence,
                )
            )

    # -------------------------------------------------------------------------
    # MULTI-METRIC DIAGNOSTIC REASONING & CORRELATION
    # -------------------------------------------------------------------------

    def _correlate_device_indicators(
        self,
        dev_id: Optional[str],
        cpu_peak: Optional[float],
        mem_peak: Optional[float],
        status: Optional[str],
        errs_peak: Optional[int],
        drops_peak: Optional[int],
        th: InfrastructureThresholds,
        findings: List[InfrastructureFinding],
        evidence_items: List[EvidenceItem],
    ) -> None:
        """
        Cross-correlates indicators for a single device to synthesize higher-order diagnostic insights.
        Does not declare device faulty based on one weak metric alone.
        """
        dev_str = f" on {dev_id}" if dev_id else ""
        dev_label = f"Device '{dev_id}': " if dev_id else ""

        # 1. Compute Saturation + Buffer Exhaustion => Hardware Overload
        if cpu_peak is not None and drops_peak is not None:
            if cpu_peak > th.cpu_warn_pct and drops_peak > th.queue_drops_warn:
                is_crit = cpu_peak > th.cpu_crit_pct or drops_peak > th.queue_drops_crit
                sev = InfrastructureSeverity.CRITICAL.value if is_crit else InfrastructureSeverity.WARNING.value
                evidence = (
                    f"{dev_label}Simultaneous compute saturation (CPU {cpu_peak:.1f}%) and "
                    f"packet tail drops ({drops_peak}) detected."
                )
                explanation = (
                    "Control plane CPU exhaustion is directly correlating with packet buffer overflow. "
                    "Software scheduling delays prevent timely dequeuing of ingress frames."
                )
                impact = "Compound forwarding bottleneck: high RTT latency, packet drop, and risk of management session timeouts."
                findings.append(
                    InfrastructureFinding(
                        metric="composite_hardware_overload",
                        observed_value=f"CPU: {cpu_peak:.1f}%, Drops: {drops_peak}",
                        threshold=f"CPU <= {th.cpu_warn_pct}%, Drops = 0",
                        severity=sev,
                        title=f"Critical CPU Overload & Buffer Saturation{dev_str}",
                        evidence=evidence,
                        explanation=explanation,
                        probable_impact=impact,
                        confidence=0.96,
                        device_id=dev_id,
                        metrics={"cpu_pct": cpu_peak, "queue_drops": drops_peak},
                    )
                )

        # 2. Memory Exhaustion + Degraded/Offline Status => Resource Collapse
        if mem_peak is not None and status is not None:
            status_lower = status.lower()
            is_impaired = status_lower in [x.lower() for x in th.device_status_warning + th.device_status_critical]
            if mem_peak > th.memory_warn_pct and is_impaired:
                evidence = (
                    f"{dev_label}Elevated memory utilization ({mem_peak:.1f}%) accompanied by "
                    f"impaired operational status '{status}'."
                )
                explanation = (
                    "System RAM depletion is directly impairing device stability, causing daemon crashes "
                    "or forcing device reboots."
                )
                impact = "Imminent total device failure, routing process death, or kernel panic."
                findings.append(
                    InfrastructureFinding(
                        metric="composite_resource_exhaustion",
                        observed_value=f"Memory: {mem_peak:.1f}%, Status: {status}",
                        threshold=f"Memory <= {th.memory_warn_pct}%, Status: online",
                        severity=InfrastructureSeverity.CRITICAL.value,
                        title=f"Critical Memory Exhaustion & Operational Impairment{dev_str}",
                        evidence=evidence,
                        explanation=explanation,
                        probable_impact=impact,
                        confidence=0.95,
                        device_id=dev_id,
                        metrics={"memory_pct": mem_peak, "device_status": status},
                    )
                )

    # -------------------------------------------------------------------------
    # SUMMARIES & NORMALIZATION
    # -------------------------------------------------------------------------

    def _build_device_summaries(
        self,
        df: pd.DataFrame,
        findings: List[InfrastructureFinding],
        th: InfrastructureThresholds,
    ) -> Dict[str, Dict[str, Any]]:
        summaries: Dict[str, Dict[str, Any]] = {}
        analyzed_devices = df["device_id"].unique().tolist() if "device_id" in df.columns else ["unknown"]

        for dev in analyzed_devices:
            dev_df = df[df["device_id"] == dev] if "device_id" in df.columns else df
            dev_findings = [f for f in findings if f.device_id == dev or (not f.device_id and len(analyzed_devices) == 1)]

            has_crit = any(f.severity.lower() == InfrastructureSeverity.CRITICAL.value for f in dev_findings)
            has_warn = any(f.severity.lower() == InfrastructureSeverity.WARNING.value for f in dev_findings)

            if has_crit:
                dev_status = InfrastructureStatus.CRITICAL.value
            elif has_warn:
                dev_status = InfrastructureStatus.DEGRADED.value
            else:
                dev_status = InfrastructureStatus.HEALTHY.value

            metrics_summary = {}
            for col in ["cpu_utilization_percent", "cpu_util_pct"]:
                if col in dev_df.columns and dev_df[col].notna().any():
                    metrics_summary["max_cpu_pct"] = round(float(dev_df[col].dropna().max()), 1)
                    break
            for col in ["memory_utilization_percent", "memory_util_pct"]:
                if col in dev_df.columns and dev_df[col].notna().any():
                    metrics_summary["max_memory_pct"] = round(float(dev_df[col].dropna().max()), 1)
                    break
            if "interface_errors" in dev_df.columns and dev_df["interface_errors"].notna().any():
                metrics_summary["max_interface_errors"] = int(dev_df["interface_errors"].dropna().max())
            if "queue_drops" in dev_df.columns and dev_df["queue_drops"].notna().any():
                metrics_summary["max_queue_drops"] = int(dev_df["queue_drops"].dropna().max())
            if "device_status" in dev_df.columns and dev_df["device_status"].notna().any():
                metrics_summary["device_status"] = str(dev_df["device_status"].dropna().iloc[-1])

            summaries[dev] = {
                "device_id": dev,
                "status": dev_status,
                "record_count": len(dev_df),
                "anomaly_count": len([f for f in dev_findings if f.severity != InfrastructureSeverity.INFO.value]),
                "metrics_summary": metrics_summary,
            }

        return summaries

    def _formulate_summary(
        self,
        overall_status: str,
        findings: List[InfrastructureFinding],
        devices: List[str],
        record_count: int,
    ) -> str:
        dev_count = len(devices)
        if overall_status == InfrastructureStatus.HEALTHY.value:
            return f"Infrastructure health is nominal across {dev_count} device(s) ({record_count} telemetry samples evaluated). Compute load, memory, and interfaces are operating normally."

        anomalies = [f"{f.metric} ({f.severity})" for f in findings if f.severity != InfrastructureSeverity.INFO.value]
        return (
            f"Infrastructure health assessment: {overall_status.upper()}. "
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

            # Validate CPU
            cpu_key = "cpu_utilization_percent" if "cpu_utilization_percent" in item else "cpu_util_pct"
            if cpu_key in item and item[cpu_key] is not None:
                try:
                    val = float(item[cpu_key])
                    if val < 0.0 or val > 100.0:
                        item_errors.append(f"Item #{idx} ({dev_id}): CPU utilization must be in 0-100% ({val})")
                except (ValueError, TypeError):
                    item_errors.append(f"Item #{idx} ({dev_id}): CPU utilization must be numeric")

            # Validate Memory
            mem_key = "memory_utilization_percent" if "memory_utilization_percent" in item else "memory_util_pct"
            if mem_key in item and item[mem_key] is not None:
                try:
                    val = float(item[mem_key])
                    if val < 0.0 or val > 100.0:
                        item_errors.append(f"Item #{idx} ({dev_id}): memory utilization must be in 0-100% ({val})")
                except (ValueError, TypeError):
                    item_errors.append(f"Item #{idx} ({dev_id}): memory utilization must be numeric")

            # Validate Interface errors
            if "interface_errors" in item and item["interface_errors"] is not None:
                try:
                    val = int(item["interface_errors"])
                    if val < 0:
                        item_errors.append(f"Item #{idx} ({dev_id}): interface_errors cannot be negative ({val})")
                except (ValueError, TypeError):
                    item_errors.append(f"Item #{idx} ({dev_id}): interface_errors must be integer")

            # Validate Queue drops
            if "queue_drops" in item and item["queue_drops"] is not None:
                try:
                    val = int(item["queue_drops"])
                    if val < 0:
                        item_errors.append(f"Item #{idx} ({dev_id}): queue_drops cannot be negative ({val})")
                except (ValueError, TypeError):
                    item_errors.append(f"Item #{idx} ({dev_id}): queue_drops must be integer")

            # Validate Availability
            if "device_availability" in item and item["device_availability"] is not None:
                try:
                    val = float(item["device_availability"])
                    if val < 0.0 or val > 100.0:
                        item_errors.append(f"Item #{idx} ({dev_id}): device_availability must be in 0-100% ({val})")
                except (ValueError, TypeError):
                    item_errors.append(f"Item #{idx} ({dev_id}): device_availability must be numeric")

            if item_errors:
                validation_errors.extend(item_errors)
            else:
                valid_records.append(item)

        return valid_records, validation_errors
