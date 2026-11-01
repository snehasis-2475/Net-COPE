from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid

from pydantic import ValidationError

from .models import (
    AgentMessage,
    AgentStatus,
    EvidenceItem,
    Finding,
    Severity,
)


def create_agent_message(
    task_id: str,
    agent_id: str,
    status: AgentStatus = AgentStatus.SUCCESS,
    findings: Optional[List[Finding]] = None,
    evidence: Optional[List[EvidenceItem]] = None,
    confidence: float = 1.0,
    errors: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> AgentMessage:
    """Helper to construct a standardized AgentMessage."""
    # Strict validation policy: invalid confidence values are rejected, not silently clamped.
    # Missing confidence retains the documented conservative default of 0.0.
    conf_val = 0.0 if confidence is None else confidence

    return AgentMessage(
        message_id=str(uuid.uuid4()),
        task_id=task_id,
        agent_id=agent_id,
        timestamp=datetime.now(timezone.utc),
        status=status,
        findings=findings or [],
        evidence=evidence or [],
        confidence=conf_val,
        errors=errors or [],
        metadata=metadata or {},
    )


def create_error_message(
    task_id: str,
    agent_id: str,
    error_desc: str,
    status: AgentStatus = AgentStatus.ERROR,
) -> AgentMessage:
    """Helper to construct an error or timeout message from an agent."""
    return AgentMessage(
        message_id=str(uuid.uuid4()),
        task_id=task_id,
        agent_id=agent_id,
        timestamp=datetime.now(timezone.utc),
        status=status,
        findings=[],
        evidence=[],
        confidence=0.0,
        errors=[error_desc],
        metadata={"error_occurred": True},
    )


def validate_message(raw_data: Any) -> AgentMessage:
    """
    Validate raw dict or JSON string against AgentMessage schema.
    Raises ValueError on validation failure.
    """
    if hasattr(raw_data, "to_agent_message"):
        return raw_data.to_agent_message()
    elif isinstance(raw_data, AgentMessage):
        return raw_data
    elif hasattr(raw_data, "model_dump"):
        data = raw_data.model_dump()
    elif isinstance(raw_data, str):
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Malformed JSON payload: {exc}") from exc
    elif isinstance(raw_data, dict):
        data = raw_data
    else:
        raise ValueError(f"Unsupported message type: {type(raw_data)}")

    try:
        return AgentMessage.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"AgentMessage schema validation failed: {exc}") from exc


def serialize_message(message: AgentMessage) -> str:
    """Serialize AgentMessage to standard JSON string."""
    return message.model_dump_json(indent=2)


def deserialize_message(json_str: str) -> AgentMessage:
    """Deserialize JSON string into AgentMessage."""
    return validate_message(json_str)
