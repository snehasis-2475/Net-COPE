from __future__ import annotations

import abc
import logging
import time
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from communication.models import (
    AgentMessage,
    AgentStatus,
    EvidenceItem,
    Finding,
    NetworkTelemetryRecord,
    Severity,
)
from communication.protocol import create_agent_message, create_error_message

logger = logging.getLogger(__name__)


class BaseAgent(abc.ABC):
    """
    Abstract Base Agent enforcing:
    1. Standardized input conversion (DataFrame / records)
    2. Resilient execution with try-except safety
    3. Standardized Pydantic AgentMessage output
    4. Execution duration and performance tracking
    """

    def __init__(self, agent_id: str, name: str, description: str):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.logger = logging.getLogger(f"agent.{agent_id}")

    def execute(
        self,
        task_id: str,
        telemetry: Union[pd.DataFrame, List[NetworkTelemetryRecord], List[Dict[str, Any]]],
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentMessage:
        """
        Executes diagnostic analysis on provided telemetry dataset.
        Guarantees an AgentMessage return even if an unhandled error occurs.
        """
        start_time = time.perf_counter()
        context = context or {}

        try:
            df = self._to_dataframe(telemetry)
            if df.empty:
                return create_agent_message(
                    task_id=task_id,
                    agent_id=self.agent_id,
                    status=AgentStatus.INSUFFICIENT_DATA,
                    findings=[
                        Finding(
                            category=self.agent_id.upper(),
                            title="Empty Telemetry Dataset",
                            description="No telemetry records were provided for analysis.",
                            severity=Severity.INFO,
                        )
                    ],
                    evidence=[],
                    confidence=0.0,
                    errors=["Telemetry record set is empty."],
                    metadata={"execution_time_ms": round((time.perf_counter() - start_time) * 1000, 2)},
                )

            # Concrete agent analysis
            findings, evidence, confidence, errors = self.analyze(df, context)

            status = AgentStatus.SUCCESS
            if errors:
                status = AgentStatus.WARNING if findings else AgentStatus.ERROR
            elif not findings:
                status = AgentStatus.SUCCESS

            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            metadata = {
                "agent_name": self.name,
                "record_count": len(df),
                "execution_time_ms": execution_time_ms,
            }

            return create_agent_message(
                task_id=task_id,
                agent_id=self.agent_id,
                status=status,
                findings=findings,
                evidence=evidence,
                confidence=confidence,
                errors=errors,
                metadata=metadata,
            )

        except Exception as exc:
            self.logger.exception(f"Unhandled exception in agent {self.agent_id}: {exc}")
            execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
            err_msg = create_error_message(
                task_id=task_id,
                agent_id=self.agent_id,
                error_desc=f"Agent runtime error: {str(exc)}",
                status=AgentStatus.ERROR,
            )
            err_msg.metadata = {
                "agent_name": self.name,
                "execution_time_ms": execution_time_ms,
            }
            return err_msg

    @abc.abstractmethod
    def analyze(
        self,
        df: pd.DataFrame,
        context: Dict[str, Any],
    ) -> tuple[List[Finding], List[EvidenceItem], float, List[str]]:
        """
        Subclasses implement domain-specific diagnostic logic.
        Returns: (findings, evidence, confidence, errors)
        """
        raise NotImplementedError

    def _to_dataframe(
        self,
        telemetry: Any,
    ) -> pd.DataFrame:
        """Converts heterogeneous telemetry representations to a clean pandas DataFrame."""
        if isinstance(telemetry, pd.DataFrame):
            return telemetry.copy()
        if isinstance(telemetry, dict):
            return pd.DataFrame([telemetry])
        if hasattr(telemetry, "model_dump"):
            return pd.DataFrame([telemetry.model_dump()])
        if isinstance(telemetry, list):
            if not telemetry:
                return pd.DataFrame()
            records = []
            for item in telemetry:
                if hasattr(item, "model_dump"):
                    records.append(item.model_dump())
                elif isinstance(item, dict):
                    records.append(item)
            return pd.DataFrame(records) if records else pd.DataFrame()
        return pd.DataFrame()
