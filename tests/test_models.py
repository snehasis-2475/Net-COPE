import json
import pytest
from pydantic import ValidationError

from communication.models import (
    AgentMessage,
    AgentStatus,
    EvidenceItem,
    Finding,
    NetworkTelemetryRecord,
    Severity,
    TelemetryBatch,
)
from communication.protocol import (
    create_agent_message,
    create_error_message,
    deserialize_message,
    serialize_message,
    validate_message,
)


def test_agent_message_creation_and_defaults():
    msg = create_agent_message(
        task_id="TASK-101",
        agent_id="test_agent",
        status=AgentStatus.SUCCESS,
        confidence=0.85,
    )
    assert msg.task_id == "TASK-101"
    assert msg.agent_id == "test_agent"
    assert msg.status == AgentStatus.SUCCESS
    assert msg.confidence == 0.85
    assert len(msg.message_id) > 0
    assert len(msg.errors) == 0


def test_confidence_strict_rejection_of_invalid_values():
    """
    Strict validation policy: invalid confidence values are rejected, not silently clamped.
    Both direct AgentMessage construction and create_agent_message() must strictly reject:
    - -0.1
    - 1.1
    - NaN
    - positive infinity
    - negative infinity
    - invalid string
    """
    invalid_values = [
        -0.1,
        1.1,
        float("nan"),
        float("inf"),
        float("-inf"),
        "invalid string",
    ]

    for val in invalid_values:
        # 1. Direct AgentMessage construction
        with pytest.raises(ValidationError):
            AgentMessage(task_id="T1", agent_id="A1", confidence=val)

        # 2. Helper create_agent_message()
        with pytest.raises(ValidationError):
            create_agent_message(task_id="T1", agent_id="A1", confidence=val)


def test_confidence_valid_values_and_conservative_default():
    """Valid confidence values are preserved and missing confidence defaults to 0.0."""
    # Preserves valid confidence values
    msg1 = AgentMessage(task_id="T1", agent_id="A1", confidence=0.85)
    assert msg1.confidence == 0.85
    msg2 = create_agent_message(task_id="T1", agent_id="A1", confidence=0.85)
    assert msg2.confidence == 0.85

    # Boundary values 0.0 and 1.0
    assert AgentMessage(task_id="T1", agent_id="A1", confidence=0.0).confidence == 0.0
    assert AgentMessage(task_id="T1", agent_id="A1", confidence=1.0).confidence == 1.0
    assert create_agent_message(task_id="T1", agent_id="A1", confidence=0.0).confidence == 0.0
    assert create_agent_message(task_id="T1", agent_id="A1", confidence=1.0).confidence == 1.0

    # Missing confidence retains documented conservative default of 0.0
    assert AgentMessage(task_id="T1", agent_id="A1").confidence == 0.0
    assert AgentMessage(task_id="T1", agent_id="A1", confidence=None).confidence == 0.0
    assert create_agent_message(task_id="T1", agent_id="A1", confidence=None).confidence == 0.0


def test_message_serialization_and_deserialization():
    finding = Finding(
        category="PERFORMANCE",
        title="High Latency",
        description="RTT breached 100ms",
        severity=Severity.HIGH,
        affected_devices=["router-1"],
    )
    evidence = EvidenceItem(
        metric_name="latency_ms",
        observed_value=120.5,
        threshold=50.0,
        unit="ms",
    )
    msg = create_agent_message(
        task_id="TASK-999",
        agent_id="perf_agent",
        findings=[finding],
        evidence=[evidence],
        confidence=0.90,
    )

    json_str = serialize_message(msg)
    assert "TASK-999" in json_str
    assert "High Latency" in json_str

    restored = deserialize_message(json_str)
    assert restored.task_id == "TASK-999"
    assert len(restored.findings) == 1
    assert restored.findings[0].title == "High Latency"
    assert restored.evidence[0].observed_value == 120.5


def test_validate_message_error_handling():
    with pytest.raises(ValueError, match="Malformed JSON payload"):
        validate_message("{invalid json")

    with pytest.raises(ValueError, match="Unsupported message type"):
        validate_message(12345)

    with pytest.raises(ValueError, match="AgentMessage schema validation failed"):
        # Missing required task_id and agent_id
        validate_message({"status": "SUCCESS"})


def test_create_error_message():
    err_msg = create_error_message(
        task_id="TASK-ERR",
        agent_id="failing_agent",
        error_desc="Socket timeout",
        status=AgentStatus.TIMEOUT,
    )
    assert err_msg.status == AgentStatus.TIMEOUT
    assert err_msg.confidence == 0.0
    assert "Socket timeout" in err_msg.errors
    assert err_msg.metadata.get("error_occurred") is True


def test_network_telemetry_record_validation():
    valid = NetworkTelemetryRecord(
        device_id="switch-01",
        latency_ms=15.2,
        cpu_util_pct=45.0,
    )
    assert valid.device_id == "switch-01"
    assert valid.latency_ms == 15.2

    with pytest.raises(ValidationError):
        # Latency cannot be negative
        NetworkTelemetryRecord(device_id="switch-01", latency_ms=-10.0)

    with pytest.raises(ValidationError):
        # CPU util cannot exceed 100%
        NetworkTelemetryRecord(device_id="switch-01", cpu_util_pct=150.0)
