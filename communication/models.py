from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentStatus(str, Enum):
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class Severity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EvidenceItem(BaseModel):
    """Structured evidence piece supporting an agent's finding."""
    metric_name: str = Field(..., description="Name of the evaluated telemetry metric")
    observed_value: Any = Field(..., description="Value observed during analysis")
    threshold: Optional[Any] = Field(default=None, description="Configured normal threshold or baseline")
    unit: Optional[str] = Field(default="", description="Unit of measurement (ms, %, Mbps, etc.)")
    device_id: Optional[str] = Field(default=None, description="Associated device identifier")
    details: Optional[str] = Field(default=None, description="Detailed explanatory context")


class Finding(BaseModel):
    """Diagnostic finding identified by an agent."""
    finding_id: str = Field(default_factory=lambda: f"FND-{uuid.uuid4().hex[:8].upper()}")
    category: str = Field(..., description="Category: PERFORMANCE, INFRASTRUCTURE, CONNECTIVITY, CORRELATION")
    title: str = Field(..., description="Short descriptive finding title")
    description: str = Field(..., description="In-depth description of the observed issue")
    severity: Severity = Field(default=Severity.MEDIUM, description="Impact severity")
    affected_devices: List[str] = Field(default_factory=list, description="List of affected device IDs")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Key metric values summary")
    metric_name: Optional[str] = Field(default=None, description="Primary metric evaluated")
    observed_value: Optional[Any] = Field(default=None, description="Observed metric value")
    threshold_value: Optional[Any] = Field(default=None, description="Threshold or baseline value")
    source_agent: Optional[str] = Field(default=None, description="Publishing agent identifier")
    interface_name: Optional[str] = Field(default=None, description="Associated network interface if applicable")
    finding_type: str = Field(default="OBSERVED_EVIDENCE", description="OBSERVED_EVIDENCE or INFERRED_HYPOTHESIS")
    timestamp: Optional[datetime] = Field(default=None, description="Timestamp of finding observation")


class AgentMessage(BaseModel):
    """
    Standardized interoperability message envelope for inter-agent communication.
    Guarantees consistent JSON representation across all system components.
    """
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str = Field(..., description="Global diagnosis task identifier")
    agent_id: str = Field(..., description="Identifier of the publishing agent")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: AgentStatus = Field(default=AgentStatus.SUCCESS)
    findings: List[Finding] = Field(default_factory=list)
    evidence: List[EvidenceItem] = Field(default_factory=list)
    confidence: float = Field(default=0.0, description="Confidence score between 0.0 and 1.0")
    errors: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("confidence", mode="before")
    @classmethod
    def validate_confidence(cls, v: Any) -> float:
        """
        Validates confidence score adherence to [0.0, 1.0] domain without silent clamping.
        Missing values (None) default to 0.0 per schema specification.
        """
        if v is None:
            return 0.0
        if isinstance(v, bool):
            raise ValueError("Confidence cannot be boolean")
        try:
            val = float(v)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Confidence value '{v}' cannot be parsed as float: {exc}") from exc
        import math
        if math.isnan(val) or math.isinf(val):
            raise ValueError(f"Confidence value '{v}' must be a finite float")
        if val < 0.0 or val > 1.0:
            raise ValueError(f"Confidence value {val} out of bounds (must be between 0.0 and 1.0)")
        return round(val, 4)

    model_config = ConfigDict(populate_by_name=True)


class NetworkTelemetryRecord(BaseModel):
    """Single network telemetry record point across time and devices."""
    timestamp: Optional[Union[str, datetime]] = Field(default=None)
    device_id: str = Field(..., description="Device identifier (e.g., router-core-01)")
    device_type: Optional[str] = Field(default="generic", description="router, switch, ap, gateway, endpoint")

    # Performance metrics
    latency_ms: Optional[float] = Field(default=None, ge=0)
    jitter_ms: Optional[float] = Field(default=None, ge=0)
    packet_loss_pct: Optional[float] = Field(default=None, ge=0, le=100)
    throughput_mbps: Optional[float] = Field(default=None, ge=0)
    bandwidth_util_pct: Optional[float] = Field(default=None, ge=0, le=100)

    # Infrastructure metrics
    device_availability: Optional[float] = Field(default=None, ge=0, le=100)
    cpu_util_pct: Optional[float] = Field(default=None, ge=0, le=100)
    memory_util_pct: Optional[float] = Field(default=None, ge=0, le=100)
    interface_status: Optional[str] = Field(default="up")  # "up", "down", "flapping"
    interface_errors: Optional[int] = Field(default=None, ge=0)
    queue_drops: Optional[int] = Field(default=None, ge=0)

    # Connectivity metrics
    dns_resolution_status: Optional[str] = Field(default="success")  # "success", "timeout", "servfail", "refused"
    dns_latency_ms: Optional[float] = Field(default=None, ge=0)
    dhcp_status: Optional[str] = Field(default="bound")  # "bound", "timeout", "failed", "exhausted"
    wifi_rssi_dbm: Optional[float] = Field(default=None)  # e.g., -45 dBm (good) to -90 dBm (poor)
    wifi_snr_db: Optional[float] = Field(default=None)
    connectivity_status: Optional[str] = Field(default="connected")  # "connected", "degraded", "disconnected"


class TelemetryBatch(BaseModel):
    """Batch container for incoming network telemetry datasets."""
    batch_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    scenario_name: Optional[str] = Field(default="custom", description="Scenario tag if predefined")
    records: List[NetworkTelemetryRecord] = Field(..., min_length=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)
