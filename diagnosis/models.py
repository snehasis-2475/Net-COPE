from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from communication.models import AgentMessage, AgentStatus, EvidenceItem, Finding, Severity


class NetworkHealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class CorrelationConfig(BaseModel):
    """
    Validated configuration settings for Fault Correlation Agent.
    Controls correlation time window, minimum required evidence, and confidence calibrations.
    """
    model_config = ConfigDict(populate_by_name=True)

    correlation_window_seconds: float = Field(
        default=300.0,
        ge=10.0,
        description="Maximum time difference between findings to be correlated as part of the same incident (seconds)",
    )
    min_supporting_findings: int = Field(
        default=1,
        ge=1,
        description="Minimum number of corroborating findings required to form a high-confidence hypothesis",
    )
    min_confidence_threshold: float = Field(
        default=0.35,
        ge=0.0,
        le=1.0,
        description="Confidence threshold below which diagnosis is flagged as indeterminate (insufficient evidence)",
    )
    high_confidence_threshold: float = Field(
        default=0.80,
        ge=0.0,
        le=1.0,
        description="Confidence threshold above which incident is confirmed with high diagnostic assurance",
    )
    multi_agent_boost: float = Field(
        default=0.10,
        ge=0.0,
        le=0.30,
        description="Confidence bonus when independent specialized agents corroborate the same root cause",
    )
    conflict_penalty: float = Field(
        default=0.20,
        ge=0.0,
        le=0.50,
        description="Confidence deduction when contradictory symptoms or healthy indicators are observed",
    )


class RootCauseCandidate(BaseModel):
    """
    Hypothesized root cause with supporting/conflicting evidence.
    Serves as the structured diagnostic hypothesis conforming to Milestone 6 requirements.
    """
    model_config = ConfigDict(populate_by_name=True)

    hypothesis_id: str = Field(default_factory=lambda: f"HYP-{uuid.uuid4().hex[:6].upper()}")
    root_cause_id: str = Field(default_factory=lambda: f"RC-{uuid.uuid4().hex[:6].upper()}")
    title: str = Field(..., description="Root cause summary name")
    probable_root_cause: str = Field(default="", description="Formal probable root cause identifier")
    category: str = Field(default="CORRELATION", description="Fault category: PERFORMANCE, INFRASTRUCTURE, CONNECTIVITY, etc.")
    description: str = Field(default="", description="Detailed causal mechanism and technical explanation")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score between 0.0 and 1.0")
    severity: str = Field(default="warning", description="Severity of the correlated incident: info, low, medium, high, critical")

    # Corroborating and contradictory evidence
    affected_devices: List[str] = Field(default_factory=list)
    supporting_findings: List[str] = Field(default_factory=list)
    supporting_agents: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    evidence_references: List[str] = Field(default_factory=list)
    supporting_symptoms: List[str] = Field(default_factory=list)
    contradicting_symptoms: List[str] = Field(default_factory=list)
    contradictory_evidence: List[str] = Field(default_factory=list, description="Contradictory evidence items or conflicting observations")

    # Uncertainty, impact, and next steps
    alternative_hypotheses: List[str] = Field(default_factory=list)
    uncertainty_explanation: str = Field(default="", description="Explanation of diagnostic ambiguities or competing explanations")
    probable_impact: str = Field(default="", description="Operational impact on business services and network performance")
    recommended_investigation: str = Field(default="", description="Prescriptive diagnostic tests to verify the hypothesis")

    @field_validator("confidence", mode="before")
    @classmethod
    def clamp_confidence(cls, v: Any) -> float:
        try:
            val = float(v)
            return max(0.0, min(1.0, val))
        except (ValueError, TypeError):
            return 0.50

    def model_post_init(self, __context: Any) -> None:
        if not self.probable_root_cause:
            self.probable_root_cause = self.title
        if not self.title and self.probable_root_cause:
            self.title = self.probable_root_cause
        if not self.description:
            self.description = f"Diagnosed incident: {self.title}."
        if not self.contradictory_evidence and self.contradicting_symptoms:
            self.contradictory_evidence = list(self.contradicting_symptoms)
        elif not self.contradicting_symptoms and self.contradictory_evidence:
            self.contradicting_symptoms = list(self.contradictory_evidence)


# Type alias for clear Milestone 6 semantic naming
CorrelationHypothesis = RootCauseCandidate


class CorrelationResponse(BaseModel):
    """
    Structured response model for Fault Correlation Agent.
    Interoperates with AgentMessage and the Central Orchestrator.
    """
    model_config = ConfigDict(populate_by_name=True)

    agent_id: str = Field(default="correlation_agent")
    task_id: str = Field(...)
    status: Union[AgentStatus, str] = Field(default=AgentStatus.SUCCESS)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    overall_health: NetworkHealthStatus = Field(default=NetworkHealthStatus.UNKNOWN)
    primary_hypothesis: Optional[CorrelationHypothesis] = Field(default=None)
    alternative_hypotheses: List[CorrelationHypothesis] = Field(default_factory=list)
    findings: List[Finding] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    errors: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    def to_agent_message(self) -> AgentMessage:
        """Adapts structured correlation response into a canonical AgentMessage."""
        meta = dict(self.metadata)
        meta.update({
            "health_status": self.overall_health.value if isinstance(self.overall_health, NetworkHealthStatus) else str(self.overall_health),
            "probable_root_cause": self.primary_hypothesis.model_dump() if self.primary_hypothesis else None,
            "alternative_causes": [alt.model_dump() for alt in self.alternative_hypotheses],
        })
        status_enum = self.status if isinstance(self.status, AgentStatus) else AgentStatus(self.status)

        return AgentMessage(
            message_id=self.message_id,
            task_id=self.task_id,
            agent_id=self.agent_id,
            status=status_enum,
            timestamp=self.timestamp,
            findings=self.findings,
            evidence=self.evidence,
            confidence=self.confidence,
            errors=self.errors,
            metadata=meta,
        )


# =============================================================================
# MILESTONE 7: REMEDIATION & RECOMMENDATION MODELS
# =============================================================================

class ActionPriority(int, Enum):
    P1_CRITICAL = 1
    P2_HIGH = 2
    P3_MEDIUM = 3
    P4_LOW = 4
    P5_PLANNING = 5


class ActionType(str, Enum):
    DIAGNOSTIC = "DIAGNOSTIC"
    MITIGATION = "IMMEDIATE_MITIGATION"
    CONFIGURATION = "CONFIGURATION"
    HARDWARE_REPAIR = "HARDWARE"
    CAPACITY_EXPANSION = "CAPACITY_EXPANSION"


class ExecutionRisk(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class CorrectiveAction(BaseModel):
    """
    Prescriptive, actionable recommendation to resolve, mitigate, or verify network anomalies.
    Complies with Milestone 7 requirements and maintains full backward-compatibility with CorrectiveAction.
    """
    model_config = ConfigDict(populate_by_name=True)

    recommendation_id: str = Field(default_factory=lambda: f"REC-{uuid.uuid4().hex[:6].upper()}")
    action_id: str = Field(default="")
    hypothesis_id: Optional[str] = Field(default=None, description="Associated hypothesis identifier")
    title: str = Field(..., description="Concise action heading")
    category: str = Field(default="DIAGNOSTIC", description="Action category e.g. DIAGNOSTIC, IMMEDIATE_MITIGATION, CONFIGURATION, HARDWARE")
    description: str = Field(..., description="Clear procedural instructions")
    affected_devices: List[str] = Field(default_factory=list)
    supporting_evidence: List[str] = Field(default_factory=list)

    priority: int = Field(default=1, ge=1, le=5, description="1 (Critical/Immediate) to 5 (Long-term hardening)")
    severity: str = Field(default="warning", description="Associated anomaly severity: info, warning, critical")
    confidence: float = Field(default=0.90, ge=0.0, le=1.0, description="Confidence in this recommendation")
    action_type: str = Field(default="DIAGNOSTIC", description="DIAGNOSTIC, IMMEDIATE_MITIGATION, CONFIGURATION, HARDWARE, CAPACITY_EXPANSION")
    execution_risk: str = Field(default="LOW", description="LOW, MEDIUM, HIGH")
    estimated_impact: str = Field(default="", description="Expected impact on performance, connectivity, and SLA")
    prerequisites: List[str] = Field(default_factory=list, description="Required checks or conditions before execution")
    verification_steps: List[str] = Field(default_factory=list, description="Step-by-step procedure to verify remediation success")
    verification_step: str = Field(default="", description="Summary of verification procedure")
    rollback_steps: List[str] = Field(default_factory=list, description="Procedure to reverse the action if unintended behavior occurs")
    requires_human_approval: bool = Field(default=False, description="True if action modifies production config or topology")
    automation_command: Optional[str] = Field(default=None, description="Executable CLI or script command")

    def model_post_init(self, __context: Any) -> None:
        if not self.action_id:
            self.action_id = self.recommendation_id
        if not self.verification_step and self.verification_steps:
            self.verification_step = " ".join(self.verification_steps)
        elif self.verification_step and not self.verification_steps:
            self.verification_steps = [self.verification_step]
        if not self.estimated_impact:
            self.estimated_impact = f"Mitigates {self.title} and restores nominal operational thresholds."

    @property
    def action_title(self) -> str:
        return self.title

    @property
    def risk_level(self) -> str:
        return self.execution_risk

    @property
    def affected_device(self) -> Optional[str]:
        return self.affected_devices[0] if self.affected_devices else None

    @property
    def preconditions(self) -> List[str]:
        return self.prerequisites


# Semantic type alias for Milestone 7
RecommendationItem = CorrectiveAction


class RecommendationAgentResponse(BaseModel):
    """
    Structured response model for Recommendation Agent.
    Interoperates with AgentMessage, DiagnosticReport, and the Central Orchestrator.
    """
    model_config = ConfigDict(populate_by_name=True)

    agent_id: str = Field(default="recommendation_agent")
    task_id: str = Field(...)
    status: Union[AgentStatus, str] = Field(default=AgentStatus.SUCCESS)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    analyzed_hypothesis_count: int = Field(default=1)
    recommendations: List[RecommendationItem] = Field(default_factory=list)
    prioritized_actions: List[RecommendationItem] = Field(default_factory=list)
    overall_summary: str = Field(default="")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    errors: List[str] = Field(default_factory=list)
    requires_human_approval: bool = Field(default=False)
    findings: List[Finding] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    def to_agent_message(self) -> AgentMessage:
        """Adapts structured recommendation response into a canonical AgentMessage."""
        meta = dict(self.metadata)
        actions_list = [a.model_dump() for a in self.prioritized_actions or self.recommendations]
        meta.update({
            "actions": actions_list,
            "recommendations": actions_list,
            "action_count": len(actions_list),
            "requires_human_approval": self.requires_human_approval,
            "overall_summary": self.overall_summary,
        })
        status_enum = self.status if isinstance(self.status, AgentStatus) else AgentStatus(self.status)

        return AgentMessage(
            message_id=self.message_id,
            task_id=self.task_id,
            agent_id=self.agent_id,
            status=status_enum,
            timestamp=self.timestamp,
            findings=self.findings,
            evidence=[],
            confidence=self.confidence,
            errors=self.errors,
            metadata=meta,
        )


class ReportLimitations(BaseModel):
    """
    Structured operational limitations, data gaps, and diagnostic caveats conforming to Milestone 10.
    """
    model_config = ConfigDict(populate_by_name=True)

    missing_telemetry: List[str] = Field(default_factory=list, description="Missing telemetry metrics or device feeds")
    invalid_records: List[str] = Field(default_factory=list, description="Isolated corrupt or malformed telemetry records")
    failed_or_timed_out_agents: List[str] = Field(default_factory=list, description="Agents that failed, timed out, or were omitted")
    insufficient_evidence: bool = Field(default=False, description="True if evidence is insufficient for decisive diagnosis")
    stale_observations: List[str] = Field(default_factory=list, description="Devices whose telemetry was stale or lagged the batch window")
    unresolved_contradictions: List[str] = Field(default_factory=list, description="Unresolved contradictions detected across agent domains")
    notes: List[str] = Field(default_factory=list, description="Explanatory notes on system limits or uncertainties")


class DiagnosticReport(BaseModel):
    """
    Unified end-to-end diagnostic report produced by the Central Orchestrator.
    Combines telemetry analysis, agent findings, causal correlation, conflict resolution,
    and prescriptive recommendations. Fully backward-compatible while meeting Milestone 10 specifications.
    """
    # Section A: Report Metadata
    report_id: str = Field(default_factory=lambda: f"REP-{uuid.uuid4().hex[:8].upper()}")
    diagnosis_id: Optional[str] = Field(default=None, description="Unique diagnosis execution ID")
    task_id: str = Field(..., description="Associated diagnostic execution task ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    execution_timestamp: Optional[datetime] = Field(default=None, description="Diagnosis execution timestamp (ISO 8601 with timezone)")
    schema_version: str = Field(default="2.0.0", description="Diagnostic report schema version")
    report_version: str = Field(default="2.0.0", description="Report structure version")
    execution_duration_ms: Optional[float] = Field(default=None, description="Total diagnostic execution time in milliseconds")
    overall_status: Optional[str] = Field(default=None, description="Overall diagnostic orchestration status: COMPLETED, COMPLETED_WITH_WARNINGS, FAILED")
    execution_status: str = Field(default="COMPLETED")

    # Section B: Executive Summary & System Health
    overall_network_health: NetworkHealthStatus = Field(default=NetworkHealthStatus.UNKNOWN)
    health_classification: str = Field(default="UNKNOWN", description="Network health classification: NOMINAL, DEGRADED, CRITICAL, UNKNOWN")
    fault_detected: bool = Field(default=False, description="True if an active network fault or degradation was detected")
    root_cause_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Confidence in the diagnosed fault root cause; None if nominal")
    diagnosis_certainty: str = Field(default="CONFIRMED", description="Hypothesis certainty tier: CONFIRMED, PROVISIONAL, INDETERMINATE, or NOT_APPLICABLE")
    confidence_interpretation: str = Field(
        default="CALIBRATED_HEURISTIC_SCORE",
        description="Interpretation mode of confidence score (calibrated heuristic score, not empirical probability)",
    )
    summary: str = Field(default="", description="Executive diagnostic summary")

    # Section C: Agent Execution Summary
    agent_execution_summary: Dict[str, Dict[str, Any]] = Field(default_factory=dict, description="Summary per agent (status, duration, findings, errors)")
    successful_agents: List[str] = Field(default_factory=list, description="List of agent IDs that completed successfully")
    failed_agents: List[str] = Field(default_factory=list, description="List of agent IDs that raised exceptions or failed")
    timed_out_agents: List[str] = Field(default_factory=list, description="List of agent IDs that timed out")
    individual_agent_findings: Dict[str, AgentMessage] = Field(default_factory=dict)
    rejected_messages: List[Dict[str, Any]] = Field(default_factory=list, description="Invalid messages rejected during validation")

    # Section D: Evidence and Findings
    validated_findings: List[Finding] = Field(default_factory=list, description="Consolidated validated findings with evidence vs inference distinction")
    supporting_evidence: List[EvidenceItem] = Field(default_factory=list)
    conflicting_evidence: List[Dict[str, Any]] = Field(default_factory=list, description="Explicit cross-agent contradictions detected and resolved")

    # Section E: Root-Cause Analysis
    probable_root_cause: Optional[RootCauseCandidate] = Field(default=None)
    selected_root_cause: Optional[RootCauseCandidate] = Field(default=None, description="Selected primary root-cause hypothesis")
    alternative_causes: List[RootCauseCandidate] = Field(default_factory=list)
    alternative_hypotheses: List[RootCauseCandidate] = Field(default_factory=list, description="Preserved alternative hypotheses")
    root_cause_hypotheses: List[RootCauseCandidate] = Field(default_factory=list, description="All evaluated root-cause hypotheses")
    affected_devices: List[str] = Field(default_factory=list)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Confidence in selected root cause")
    uncertainty_notes: List[str] = Field(default_factory=list, description="Notes on unresolved uncertainty or contradictions")

    # Section F: Corrective Recommendations
    recommended_corrective_actions: List[CorrectiveAction] = Field(default_factory=list)
    recommendations: List[CorrectiveAction] = Field(default_factory=list, description="Prioritized recommendations")

    # Section G: Limitations and Warnings
    limitations: ReportLimitations = Field(default_factory=ReportLimitations, description="Structured operational limitations and data gaps")
    warnings: List[str] = Field(default_factory=list, description="Warning notices identified during diagnosis")
    errors: List[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)

    @model_validator(mode="after")
    def _sync_report_fields(self) -> DiagnosticReport:
        """Ensures bidirectional synchronization between original, Milestone 9, and Milestone 10 fields."""
        # Sync IDs and timestamps
        if not self.diagnosis_id:
            self.diagnosis_id = self.report_id
        if not self.report_id:
            self.report_id = self.diagnosis_id
        if not self.execution_timestamp:
            self.execution_timestamp = self.timestamp
        if not self.timestamp:
            self.timestamp = self.execution_timestamp

        # Sync statuses
        if not self.overall_status:
            self.overall_status = self.execution_status
        if not self.execution_status:
            self.execution_status = self.overall_status

        # Sync root causes
        if self.selected_root_cause is None and self.probable_root_cause is not None:
            self.selected_root_cause = self.probable_root_cause
        elif self.probable_root_cause is None and self.selected_root_cause is not None:
            self.probable_root_cause = self.selected_root_cause

        # Sync confidence
        if self.confidence is None:
            self.confidence = self.confidence_score
        else:
            self.confidence_score = self.confidence

        if self.selected_root_cause is not None and self.confidence is not None:
            self.selected_root_cause.confidence = self.confidence
        if self.probable_root_cause is not None and self.confidence_score is not None:
            self.probable_root_cause.confidence = self.confidence_score

        # Sync hypotheses
        if not self.alternative_hypotheses and self.alternative_causes:
            self.alternative_hypotheses = list(self.alternative_causes)
        elif not self.alternative_causes and self.alternative_hypotheses:
            self.alternative_causes = list(self.alternative_hypotheses)

        if not self.root_cause_hypotheses and self.selected_root_cause:
            self.root_cause_hypotheses = [self.selected_root_cause] + self.alternative_hypotheses

        # Sync recommendations
        if not self.recommendations and self.recommended_corrective_actions:
            self.recommendations = list(self.recommended_corrective_actions)
        elif not self.recommended_corrective_actions and self.recommendations:
            self.recommended_corrective_actions = list(self.recommendations)

        # Compute fault_detected flag and health_classification
        if self.overall_network_health in [NetworkHealthStatus.DEGRADED, NetworkHealthStatus.CRITICAL]:
            self.fault_detected = True
            self.health_classification = self.overall_network_health.value
        elif self.overall_network_health == NetworkHealthStatus.HEALTHY:
            self.fault_detected = False
            self.health_classification = "NOMINAL"
        elif self.overall_network_health == NetworkHealthStatus.UNKNOWN:
            self.fault_detected = False
            self.health_classification = "UNKNOWN"
        else:
            self.fault_detected = bool(
                self.selected_root_cause and self.selected_root_cause.category not in ["NOMINAL", "UNKNOWN"]
            )
            self.health_classification = "NOMINAL" if not self.fault_detected else "DEGRADED"

        # Decouple diagnostic hypothesis certainty from network health status:
        # NOMINAL describes network health. CONFIRMED, PROVISIONAL, and INDETERMINATE apply strictly to diagnostic hypotheses.
        if self.overall_network_health == NetworkHealthStatus.UNKNOWN:
            self.diagnosis_certainty = "INDETERMINATE"
            self.root_cause_confidence = None
        elif not self.fault_detected or (self.selected_root_cause and self.selected_root_cause.category == "NOMINAL"):
            self.diagnosis_certainty = "NOT_APPLICABLE"
            self.root_cause_confidence = None
        elif self.confidence and self.confidence >= 0.80:
            self.diagnosis_certainty = "CONFIRMED"
            self.root_cause_confidence = self.confidence
        elif self.confidence and self.confidence >= 0.40:
            self.diagnosis_certainty = "PROVISIONAL"
            self.root_cause_confidence = self.confidence
        else:
            self.diagnosis_certainty = "INDETERMINATE"
            self.root_cause_confidence = self.confidence

        return self
