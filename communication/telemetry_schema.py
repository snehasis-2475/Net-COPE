from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Union
import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DeviceType(str, Enum):
    ROUTER = "router"
    SWITCH = "switch"
    ACCESS_POINT = "access_point"
    AP = "ap"
    ENDPOINT = "endpoint"
    GATEWAY = "gateway"
    FIREWALL = "firewall"
    SERVER = "server"
    WORKSTATION = "workstation"
    GENERIC = "generic"


class DeviceStatus(str, Enum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    REBOOTING = "rebooting"
    UP = "up"
    DOWN = "down"
    HEALTHY = "healthy"


class DNSStatus(str, Enum):
    SUCCESS = "success"
    TIMEOUT = "timeout"
    SERVFAIL = "servfail"
    REFUSED = "refused"
    NXDOMAIN = "nxdomain"
    FAILED = "failed"


class DHCPStatus(str, Enum):
    BOUND = "bound"
    TIMEOUT = "timeout"
    FAILED = "failed"
    EXHAUSTED = "exhausted"
    RENEWED = "renewed"


class ConnectivityStatus(str, Enum):
    CONNECTED = "connected"
    DEGRADED = "degraded"
    DISCONNECTED = "disconnected"


class TelemetryRecord(BaseModel):
    """
    Standardized network telemetry data model for NetCoop AI.
    Serves as the common input foundation for all specialized diagnostic agents.
    """
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        use_enum_values=True,
    )

    # IDENTIFICATION
    device_id: str = Field(..., min_length=1, description="Unique identifier of network device")
    device_type: Optional[str] = Field(default="generic", description="Device role or category")
    timestamp: datetime = Field(..., description="Timestamp of telemetry collection")
    location: Optional[str] = Field(default=None, description="Physical or logical location")
    interface_name: Optional[str] = Field(default=None, description="Name of the interface, e.g. eth0, GigabitEthernet0/1")

    # PERFORMANCE
    latency_ms: Optional[float] = Field(default=None, ge=0.0, description="Round-trip transmission delay in milliseconds")
    jitter_ms: Optional[float] = Field(default=None, ge=0.0, description="Packet delay variation in milliseconds")
    packet_loss_percent: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        alias="packet_loss_pct",
        description="Packet loss percentage (0.0 to 100.0)",
    )
    throughput_mbps: Optional[float] = Field(default=None, ge=0.0, description="Observed network throughput in Mbps")
    bandwidth_utilization_percent: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        alias="bandwidth_util_pct",
        description="Link bandwidth consumption percentage (0.0 to 100.0)",
    )

    # INFRASTRUCTURE
    cpu_utilization_percent: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        alias="cpu_util_pct",
        description="Control plane / CPU utilization percentage (0.0 to 100.0)",
    )
    memory_utilization_percent: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        alias="memory_util_pct",
        description="RAM consumption percentage (0.0 to 100.0)",
    )
    device_status: Optional[str] = Field(default=None, description="Operational state: active, degraded, offline, up, down")
    interface_errors: Optional[int] = Field(default=None, ge=0, description="CRC / frame error count")
    queue_drops: Optional[int] = Field(default=None, ge=0, description="Tail drops / buffer overflow count")

    # CONNECTIVITY
    wifi_signal_dbm: Optional[float] = Field(
        default=None,
        ge=-120.0,
        le=0.0,
        alias="wifi_rssi_dbm",
        description="Received wireless signal strength (RSSI) in dBm (-120.0 to 0.0)",
    )
    dns_status: Optional[str] = Field(
        default=None,
        alias="dns_resolution_status",
        description="DNS resolution outcome: success, timeout, servfail, refused, nxdomain, failed",
    )
    dhcp_status: Optional[str] = Field(
        default=None,
        description="DHCP lease state: bound, timeout, failed, exhausted, renewed",
    )
    connectivity_status: Optional[str] = Field(
        default=None,
        description="End-to-end host reachability: connected, degraded, disconnected",
    )

    @field_validator("device_id")
    @classmethod
    def validate_device_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("device_id cannot be empty or whitespace only")
        return v.strip()

    @field_validator("timestamp", mode="before")
    @classmethod
    def validate_timestamp(cls, v: Any) -> datetime:
        if isinstance(v, datetime):
            if v.tzinfo is None:
                return v.replace(tzinfo=timezone.utc)
            return v
        if isinstance(v, (int, float)):
            # Handle epoch timestamp
            try:
                return datetime.fromtimestamp(v, tz=timezone.utc)
            except Exception as exc:
                raise ValueError(f"Invalid numeric epoch timestamp '{v}': {exc}") from exc
        if isinstance(v, str):
            v_str = v.strip()
            if not v_str:
                raise ValueError("timestamp string cannot be empty")
            # Try ISO format
            try:
                # Handle Z notation
                if v_str.endswith("Z"):
                    v_str = v_str[:-1] + "+00:00"
                dt = datetime.fromisoformat(v_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except Exception as exc:
                raise ValueError(f"Invalid timestamp format '{v}'. Must be valid ISO-8601 string: {exc}") from exc
        raise ValueError(f"Unsupported timestamp type '{type(v).__name__}'. Expected datetime or ISO string.")

    @field_validator("device_status")
    @classmethod
    def validate_device_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v_clean = str(v).strip().lower()
        valid_statuses = {s.value for s in DeviceStatus}
        if v_clean not in valid_statuses:
            raise ValueError(f"Invalid device_status '{v}'. Allowed values: {sorted(valid_statuses)}")
        return v_clean

    @field_validator("dns_status")
    @classmethod
    def validate_dns_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v_clean = str(v).strip().lower()
        valid_statuses = {s.value for s in DNSStatus}
        if v_clean not in valid_statuses:
            raise ValueError(f"Invalid dns_status '{v}'. Allowed values: {sorted(valid_statuses)}")
        return v_clean

    @field_validator("dhcp_status")
    @classmethod
    def validate_dhcp_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v_clean = str(v).strip().lower()
        valid_statuses = {s.value for s in DHCPStatus}
        if v_clean not in valid_statuses:
            raise ValueError(f"Invalid dhcp_status '{v}'. Allowed values: {sorted(valid_statuses)}")
        return v_clean

    @field_validator("connectivity_status")
    @classmethod
    def validate_connectivity_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v_clean = str(v).strip().lower()
        valid_statuses = {s.value for s in ConnectivityStatus}
        if v_clean not in valid_statuses:
            raise ValueError(f"Invalid connectivity_status '{v}'. Allowed values: {sorted(valid_statuses)}")
        return v_clean

    @field_validator("device_type")
    @classmethod
    def validate_device_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return "generic"
        v_clean = str(v).strip().lower()
        valid_types = {t.value for t in DeviceType}
        # If type not explicitly in enum, accept normalized string
        return v_clean


class TelemetryBatchSchema(BaseModel):
    """Container for batch telemetry submissions."""
    model_config = ConfigDict(populate_by_name=True)

    batch_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: Optional[str] = Field(default="ingestion_service")
    records: list[TelemetryRecord] = Field(..., min_length=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)
