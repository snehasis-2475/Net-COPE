from __future__ import annotations

import concurrent.futures
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import uuid

import pandas as pd
from pydantic import ValidationError

from agents.connectivity_agent import ConnectivityAgent
from agents.infrastructure_agent import InfrastructureAgent
from agents.performance_agent import PerformanceAgent
from agents.baseline_detector import BaselineDetector
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
    validate_message,
)
from diagnosis.correlation_agent import FaultCorrelationAgent
from diagnosis.models import (
    CorrectiveAction,
    DiagnosticReport,
    NetworkHealthStatus,
    ReportLimitations,
    RootCauseCandidate,
)
from diagnosis.recommendation_agent import RecommendationAgent

logger = logging.getLogger("orchestrator.central")


_DEFAULT_AGENT = object()


class CentralOrchestrator:
    """
    Enhanced Central Orchestrator for the NetCoop AI Multi-Agent Diagnostic System.
    Coordinates telemetry ingest, parallel agent execution, message validation,
    failure recovery, evidence-based conflict resolution, fault correlation,
    recommendation formulation, and unified report generation.
    """

    def __init__(
        self,
        agent_timeout_seconds: float = 8.0,
        reports_dir: Optional[str] = None,
        performance_agent: Any = _DEFAULT_AGENT,
        infrastructure_agent: Any = _DEFAULT_AGENT,
        connectivity_agent: Any = _DEFAULT_AGENT,
        correlation_agent: Any = _DEFAULT_AGENT,
        recommendation_agent: Any = _DEFAULT_AGENT,
        enable_baseline: bool = True,
    ):
        self.agent_timeout = agent_timeout_seconds
        self.enable_baseline = enable_baseline
        self.baseline_detector = BaselineDetector() if enable_baseline else None
        self.reports_dir = Path(reports_dir) if reports_dir else Path("reports")
        try:
            self.reports_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self.logger.warning(f"Could not create reports directory '{self.reports_dir}': {exc}")

        # Allow dependency injection while defaulting to production agents
        self.performance_agent = PerformanceAgent() if performance_agent is _DEFAULT_AGENT else performance_agent
        self.infrastructure_agent = InfrastructureAgent() if infrastructure_agent is _DEFAULT_AGENT else infrastructure_agent
        self.connectivity_agent = ConnectivityAgent() if connectivity_agent is _DEFAULT_AGENT else connectivity_agent

        # Synthesis and remediation specialists
        self.correlation_agent = FaultCorrelationAgent() if correlation_agent is _DEFAULT_AGENT else correlation_agent
        self.recommendation_agent = RecommendationAgent() if recommendation_agent is _DEFAULT_AGENT else recommendation_agent

        self.logger = logging.getLogger("orchestrator.central")

    def run_diagnosis(
        self,
        telemetry: Union[pd.DataFrame, List[Dict[str, Any]], List[NetworkTelemetryRecord], TelemetryBatch],
        scenario_name: Optional[str] = None,
        save_report: bool = True,
        enable_baseline: Optional[bool] = None,
    ) -> DiagnosticReport:
        """
        Executes end-to-end multi-agent network fault diagnosis with robust failure recovery,
        interoperability message validation, and evidence-based conflict resolution.
        """
        task_id = f"TASK-{uuid.uuid4().hex[:8].upper()}"
        report_id = f"REP-{uuid.uuid4().hex[:8].upper()}"
        start_time = time.perf_counter()
        errors: List[str] = []

        self.logger.info(f"Starting network diagnosis task {task_id} (Scenario: {scenario_name or 'custom'})")

        # 1. Telemetry validation & normalization
        df, validation_errors = self.validate_and_normalize_telemetry(telemetry)
        if validation_errors:
            errors.extend(validation_errors)

        if df.empty:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 1)
            self.logger.warning(f"Task {task_id}: Telemetry is empty or completely invalid.")
            empty_limitations = ReportLimitations(
                missing_telemetry=["Telemetry input batch contained no valid records."],
                invalid_records=errors,
                insufficient_evidence=True,
                notes=["Diagnosis aborted: input telemetry contained no valid records or failed schema validation."],
            )
            now_utc = datetime.now(timezone.utc)
            empty_report = DiagnosticReport(
                report_id=report_id,
                diagnosis_id=report_id,
                task_id=task_id,
                timestamp=now_utc,
                execution_timestamp=now_utc,
                schema_version="2.0.0",
                report_version="2.0.0",
                execution_duration_ms=duration_ms,
                overall_network_health=NetworkHealthStatus.UNKNOWN,
                fault_detected=False,
                diagnosis_certainty="INDETERMINATE",
                confidence_interpretation="CALIBRATED_HEURISTIC_SCORE",
                overall_status="FAILED",
                execution_status="FAILED",
                probable_root_cause=RootCauseCandidate(
                    title="Invalid or Empty Telemetry",
                    description="The submitted telemetry data contained no valid records or failed schema validation.",
                    confidence=0.0,
                    supporting_symptoms=[],
                    contradicting_symptoms=[],
                    affected_devices=[],
                    evidence_references=[],
                ),
                alternative_causes=[],
                affected_devices=[],
                supporting_evidence=[],
                individual_agent_findings={},
                confidence_score=0.0,
                confidence=0.0,
                recommended_corrective_actions=[
                    CorrectiveAction(
                        priority=1,
                        title="Validate Telemetry Ingestion Pipeline",
                        category="VERIFICATION",
                        description="Check that telemetry collectors are sending structured JSON or CSV with required device_id and metric columns.",
                        verification_step="Submit a valid telemetry record with device_id and latency_ms.",
                        automation_command="curl -X GET http://localhost:8000/health",
                    )
                ],
                successful_agents=[],
                failed_agents=[],
                timed_out_agents=[],
                agent_execution_summary={},
                validated_findings=[],
                rejected_messages=[],
                conflicting_evidence=[],
                uncertainty_notes=["Diagnosis aborted: input telemetry contained no valid records."],
                limitations=empty_limitations,
                warnings=["Telemetry input empty or unparseable."],
                errors=errors,
                summary="Diagnosis aborted: input telemetry failed schema validation or was empty.",
            )
            if save_report:
                try:
                    self._save_report(empty_report)
                except Exception as save_err:
                    self.logger.warning(f"Failed to persist empty report: {save_err}")
            return empty_report

        # 2. Execution Tracking & Domain Agent Parallel Execution
        agent_messages: Dict[str, AgentMessage] = {}
        agent_execution_summary: Dict[str, Dict[str, Any]] = {}
        successful_agents: List[str] = []
        failed_agents: List[str] = []
        timed_out_agents: List[str] = []
        rejected_messages: List[Dict[str, Any]] = []
        validated_findings: List[Finding] = []
        seen_message_ids: Set[str] = set()

        # 1.5 Rolling Baseline Anomaly Detection (Silent Degradation)
        active_enable_baseline = self.enable_baseline if enable_baseline is None else enable_baseline
        baseline_findings: List[Finding] = []
        baseline_evidence: List[EvidenceItem] = []

        if active_enable_baseline and not df.empty:
            detector = BaselineDetector()
            df_chrono = df.copy()
            if "timestamp" in df_chrono.columns:
                try:
                    df_chrono["_ts_dt"] = pd.to_datetime(df_chrono["timestamp"], format="mixed", utc=True, errors="coerce")
                    df_chrono = df_chrono.sort_values("_ts_dt").drop(columns=["_ts_dt"])
                except Exception:
                    pass
            records_chrono = df_chrono.to_dict(orient="records")
            for rec in records_chrono:
                anoms = detector.update_and_score(rec)
                for anom in anoms:
                    ev = EvidenceItem(
                        metric_name=anom["metric"],
                        observed_value=anom["value"],
                        threshold=anom["baseline"],
                        unit=anom.get("unit", ""),
                        device_id=anom["device_id"],
                        details=anom["description"],
                    )
                    baseline_evidence.append(ev)
                    fnd = Finding(
                        category="PERFORMANCE",
                        title=f"Rolling Baseline Anomaly: {anom['metric']} on {anom['device_id']}",
                        description=anom["description"],
                        severity=Severity.MEDIUM,
                        affected_devices=[anom["device_id"]],
                        metrics={
                            anom["metric"]: anom["value"],
                            "baseline": anom["baseline"],
                            "z_score": anom["z_score"],
                            "sustained_points": anom["sustained_points"],
                        },
                        metric_name=anom["metric"],
                        observed_value=anom["value"],
                        threshold_value=anom["baseline"],
                        source_agent="baseline_detector",
                        finding_type="OBSERVED_EVIDENCE",
                    )
                    baseline_findings.append(fnd)

        # Build list of active domain agents (handling missing optional agents)
        domain_agents = []
        if self.performance_agent is not None:
            domain_agents.append(("performance_agent", self.performance_agent))
        else:
            self.logger.warning("Optional performance_agent is not registered.")

        if self.infrastructure_agent is not None:
            domain_agents.append(("infrastructure_agent", self.infrastructure_agent))
        else:
            self.logger.warning("Optional infrastructure_agent is not registered.")

        if self.connectivity_agent is not None:
            domain_agents.append(("connectivity_agent", self.connectivity_agent))
        else:
            self.logger.warning("Optional connectivity_agent is not registered.")

        # Execute domain agents concurrently with bounded timeout
        executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max(1, len(domain_agents)),
            thread_name_prefix="netcoop-agent-worker",
        )
        try:
            future_to_agent = {
                executor.submit(self._execute_agent_timed, agent, task_id, df): agent_id
                for agent_id, agent in domain_agents
            }

            done, not_done = concurrent.futures.wait(
                future_to_agent.keys(),
                timeout=self.agent_timeout,
                return_when=concurrent.futures.ALL_COMPLETED,
            )

            for future in done:
                agent_id = future_to_agent[future]
                try:
                    raw_msg, duration_ms = future.result()

                    # Interoperability & message structure validation
                    validated_msg, rejection = self._validate_agent_message(
                        raw_msg=raw_msg,
                        expected_agent_id=agent_id,
                        task_id=task_id,
                        seen_message_ids=seen_message_ids,
                    )

                    if rejection:
                        rejected_messages.append(rejection)
                        failed_agents.append(agent_id)
                        errors.append(f"Agent {agent_id} response rejected: {rejection['reason']}")
                    else:
                        if validated_msg.status == AgentStatus.SUCCESS:
                            successful_agents.append(agent_id)
                        else:
                            failed_agents.append(agent_id)

                    agent_messages[agent_id] = validated_msg
                    # Milestone 10: Enrich findings with provenance, finding type, and timestamp
                    for f in validated_msg.findings:
                        if not f.source_agent:
                            f.source_agent = agent_id
                        if not f.finding_type:
                            f.finding_type = "OBSERVED_EVIDENCE"
                        if not f.timestamp:
                            f.timestamp = validated_msg.timestamp
                        if not f.metric_name and f.metrics:
                            first_metric = next(iter(f.metrics.keys()))
                            f.metric_name = first_metric
                            f.observed_value = f.metrics.get(first_metric)
                    validated_findings.extend(validated_msg.findings)

                    agent_execution_summary[agent_id] = {
                        "status": validated_msg.status.value,
                        "duration_ms": duration_ms,
                        "finding_count": len(validated_msg.findings),
                        "evidence_count": len(validated_msg.evidence),
                        "error_count": len(validated_msg.errors),
                        "errors": validated_msg.errors,
                    }

                except Exception as exc:
                    self.logger.exception(f"Agent {agent_id} failed with unhandled exception: {exc}")
                    err_msg = create_error_message(
                        task_id=task_id,
                        agent_id=agent_id,
                        error_desc=f"Execution failure: {str(exc)}",
                        status=AgentStatus.ERROR,
                    )
                    agent_messages[agent_id] = err_msg
                    failed_agents.append(agent_id)
                    errors.append(f"Agent {agent_id} error: {str(exc)}")
                    agent_execution_summary[agent_id] = {
                        "status": AgentStatus.ERROR.value,
                        "duration_ms": 0.0,
                        "finding_count": 0,
                        "evidence_count": 0,
                        "error_count": 1,
                        "errors": [str(exc)],
                    }

            for future in not_done:
                agent_id = future_to_agent[future]
                self.logger.error(f"Agent {agent_id} timed out after {self.agent_timeout}s.")
                timeout_msg = create_error_message(
                    task_id=task_id,
                    agent_id=agent_id,
                    error_desc=f"Agent exceeded maximum execution timeout ({self.agent_timeout}s).",
                    status=AgentStatus.TIMEOUT,
                )
                agent_messages[agent_id] = timeout_msg
                timed_out_agents.append(agent_id)
                errors.append(f"Agent {agent_id} timed out.")
                agent_execution_summary[agent_id] = {
                    "status": AgentStatus.TIMEOUT.value,
                    "duration_ms": round(self.agent_timeout * 1000, 1),
                    "finding_count": 0,
                    "evidence_count": 0,
                    "error_count": 1,
                    "errors": [f"Timeout exceeded {self.agent_timeout}s"],
                }
        finally:
            # CRITICAL: shutdown(wait=False, cancel_futures=True) releases executor control immediately.
            # Using 'with ThreadPoolExecutor' blocks in __exit__ via shutdown(wait=True), which would
            # stall run_diagnosis until blocked threads finish. shutdown(wait=False) prevents blocked
            # threads from hanging orchestrator completion while safely discarding unstarted tasks.
            #
            # THREAD LIFECYCLE LIMITATION & BOUNDED WORKER STRATEGY:
            # Python OS threads cannot safely be forcibly killed without unsafe C-API calls (e.g. PyThreadState_SetAsyncExc),
            # which risk deadlocks or corrupting interpreter state. Running worker threads therefore continue
            # harmlessly in the background until their work completes, and they cannot mutate the finalized report.
            # Under repeated timeout workloads where workers block indefinitely (e.g. un-timeouted sockets),
            # worker threads would accumulate.
            # Recommended production strategies:
            # 1. Process Isolation: For untrusted or un-timeouted agents, use ProcessPoolExecutor or containerized
            #    sidecar workers that support clean OS process-level termination (SIGKILL).
            # 2. Defensive Agent Timeouts: Ensure all domain agents enforce internal socket/HTTP timeouts smaller
            #    than the orchestrator timeout so threads terminate naturally.
            executor.shutdown(wait=False, cancel_futures=True)

        # 3. Contradiction & Conflict Resolution
        conflicting_evidence, conflict_penalty, uncertainty_notes, stale_devices = self._detect_and_resolve_conflicts(
            agent_messages=agent_messages,
            df=df,
        )

        # 4. Fault Correlation
        try:
            correlation_inputs = dict(agent_messages)
            if baseline_findings:
                correlation_inputs["baseline_detector"] = AgentMessage(
                    agent_id="baseline_detector",
                    sender_agent_id="baseline_detector",
                    task_id=task_id,
                    timestamp=datetime.now(timezone.utc),
                    status=AgentStatus.SUCCESS,
                    confidence=0.55,
                    findings=baseline_findings,
                    evidence=baseline_evidence,
                    metadata={"source": "baseline_detector", "anomaly_count": len(baseline_findings)},
                )
            correlation_raw = self.correlation_agent.correlate(task_id, correlation_inputs)
            correlation_msg, corr_rejection = self._validate_agent_message(
                raw_msg=correlation_raw,
                expected_agent_id="correlation_agent",
                task_id=task_id,
                seen_message_ids=seen_message_ids,
            )
            if corr_rejection:
                rejected_messages.append(corr_rejection)
                errors.append(f"Correlation Agent output rejected: {corr_rejection['reason']}")
            # Milestone 10: Inferred hypothesis findings enrichment (preserve domain agent findings)
            for f in correlation_msg.findings:
                if f.category == "CORRELATION" or f.source_agent in [None, "correlation_agent"]:
                    if not f.source_agent:
                        f.source_agent = "correlation_agent"
                    f.finding_type = "INFERRED_HYPOTHESIS"
                if not f.timestamp:
                    f.timestamp = correlation_msg.timestamp
            agent_messages["correlation_agent"] = correlation_msg
        except Exception as exc:
            self.logger.exception(f"Fault Correlation Agent failed: {exc}")
            correlation_msg = create_error_message(
                task_id=task_id,
                agent_id="correlation_agent",
                error_desc=f"Correlation failure: {str(exc)}",
            )
            agent_messages["correlation_agent"] = correlation_msg
            failed_agents.append("correlation_agent")
            errors.append(f"Correlation error: {str(exc)}")

        # 5. Corrective Recommendations
        try:
            recommendation_raw = self.recommendation_agent.recommend(task_id, correlation_msg)
            recommendation_msg, rec_rejection = self._validate_agent_message(
                raw_msg=recommendation_raw,
                expected_agent_id="recommendation_agent",
                task_id=task_id,
                seen_message_ids=seen_message_ids,
            )
            if rec_rejection:
                rejected_messages.append(rec_rejection)
                errors.append(f"Recommendation Agent output rejected: {rec_rejection['reason']}")
            # Milestone 10: Inferred hypothesis findings enrichment (preserve domain agent findings)
            for f in recommendation_msg.findings:
                if f.category in ["RECOMMENDATION", "ACTION"] or f.source_agent in [None, "recommendation_agent"]:
                    if not f.source_agent:
                        f.source_agent = "recommendation_agent"
                    f.finding_type = "INFERRED_HYPOTHESIS"
                if not f.timestamp:
                    f.timestamp = recommendation_msg.timestamp
            agent_messages["recommendation_agent"] = recommendation_msg
        except Exception as exc:
            self.logger.exception(f"Recommendation Agent failed: {exc}")
            recommendation_msg = create_error_message(
                task_id=task_id,
                agent_id="recommendation_agent",
                error_desc=f"Recommendation failure: {str(exc)}",
            )
            agent_messages["recommendation_agent"] = recommendation_msg
            failed_agents.append("recommendation_agent")
            errors.append(f"Recommendation error: {str(exc)}")

        # 6. Extract structured components for final unified report
        corr_meta = correlation_msg.metadata or {}
        rec_meta = recommendation_msg.metadata or {}

        # Probable root cause
        rc_candidate = None
        if "probable_root_cause" in corr_meta and corr_meta["probable_root_cause"]:
            rc_candidate = RootCauseCandidate.model_validate(corr_meta["probable_root_cause"])

        # Alternative causes
        alt_causes: List[RootCauseCandidate] = []
        if "alternative_causes" in corr_meta:
            for alt in corr_meta["alternative_causes"]:
                alt_causes.append(RootCauseCandidate.model_validate(alt))

        # Overall health
        raw_health = corr_meta.get("health_status", NetworkHealthStatus.UNKNOWN.value)
        try:
            health_status = NetworkHealthStatus(raw_health)
        except ValueError:
            health_status = NetworkHealthStatus.UNKNOWN

        # Supporting evidence consolidation (deduplicating metric duplicates)
        consolidated_evidence: List[EvidenceItem] = []
        seen_evidence_keys = set()
        if baseline_evidence:
            for e in baseline_evidence:
                ev_key = (e.device_id, e.metric_name, e.observed_value)
                if ev_key not in seen_evidence_keys:
                    seen_evidence_keys.add(ev_key)
                    consolidated_evidence.append(e)

        for msg in agent_messages.values():
            for e in msg.evidence:
                ev_key = (e.device_id, e.metric_name, e.observed_value)
                if ev_key not in seen_evidence_keys:
                    seen_evidence_keys.add(ev_key)
                    consolidated_evidence.append(e)

        # Affected devices
        affected_set = set()
        for msg in agent_messages.values():
            for f in msg.findings:
                affected_set.update(f.affected_devices)

        # Corrective actions
        actions: List[CorrectiveAction] = []
        if "actions" in rec_meta:
            for act in rec_meta["actions"]:
                actions.append(CorrectiveAction.model_validate(act))

        # Confidence Calibration & Penalty Calculation
        raw_confidence = correlation_msg.confidence if correlation_msg.confidence > 0 else 0.50

        # Penalize confidence for missing domain agents
        missing_agent_penalty = 0.10 * (len(failed_agents) + len(timed_out_agents))
        if missing_agent_penalty > 0:
            missing_names = ", ".join(failed_agents + timed_out_agents)
            uncertainty_notes.append(
                f"Confidence reduced by {missing_agent_penalty * 100:.1f}% due to {len(failed_agents) + len(timed_out_agents)} missing or failed domain agent(s): {missing_names}."
            )

        total_penalty = min(0.40, conflict_penalty + missing_agent_penalty)
        final_confidence = max(0.10, min(1.0, round(raw_confidence - total_penalty, 2)))

        # Update root cause candidate confidence if candidate exists
        if rc_candidate:
            rc_candidate.confidence = final_confidence
            if uncertainty_notes and not rc_candidate.uncertainty_explanation:
                rc_candidate.uncertainty_explanation = "; ".join(uncertainty_notes)

        # Executive summary (Milestone 10 format)
        duration_ms = round((time.perf_counter() - start_time) * 1000, 1)
        fault_detected_flag = health_status in [NetworkHealthStatus.DEGRADED, NetworkHealthStatus.CRITICAL] or bool(
            rc_candidate and rc_candidate.category != "NOMINAL"
        )
        fault_str = "Active fault detected" if fault_detected_flag else "No active faults detected (nominal conditions)"
        rc_str = f"Primary root cause: {rc_candidate.title}." if rc_candidate else "No decisive root-cause hypothesis confirmed."
        agent_tally_str = f"Agents: {len(successful_agents)} succeeded, {len(failed_agents)} failed, {len(timed_out_agents)} timed out."

        summary = (
            f"Network condition: {health_status.value}. {fault_str}. {rc_str} "
            f"Overall confidence: {final_confidence * 100:.1f}%. Affected devices: {len(affected_set)}. "
            f"{agent_tally_str} Diagnostic completed in {duration_ms}ms with {len(actions)} recommendation(s)."
        )

        if conflicting_evidence:
            summary += f" Resolved {len(conflicting_evidence)} cross-agent contradiction(s)."

        # Determine execution status
        if failed_agents or timed_out_agents or validation_errors:
            overall_status = "COMPLETED_WITH_WARNINGS"
        else:
            overall_status = "COMPLETED"

        # Limitations & Warnings Construction (Milestone 10)
        standard_metrics = [
            "cpu_utilization_pct",
            "memory_utilization_pct",
            "packet_loss_pct",
            "latency_ms",
            "jitter_ms",
            "bandwidth_util_pct",
            "dns_resolution_status",
        ]
        missing_telemetry = [m for m in standard_metrics if m not in df.columns]
        invalid_records = [str(err) for err in validation_errors]
        failed_or_timed_out = list(failed_agents) + list(timed_out_agents)
        insufficient_evidence = (final_confidence < 0.40) or (
            len(validated_findings) == 0 and health_status != NetworkHealthStatus.HEALTHY
        )
        unresolved_contradictions = [
            f"{c.get('type', 'CONTRADICTION')} on device(s) {c.get('affected_devices', [])}"
            for c in conflicting_evidence
        ]
        limitation_notes = list(uncertainty_notes)
        if missing_telemetry:
            limitation_notes.append(f"Telemetry missing standard metric columns: {', '.join(missing_telemetry)}")

        limitations = ReportLimitations(
            missing_telemetry=missing_telemetry,
            invalid_records=invalid_records,
            failed_or_timed_out_agents=failed_or_timed_out,
            insufficient_evidence=insufficient_evidence,
            stale_observations=list(stale_devices),
            unresolved_contradictions=unresolved_contradictions,
            notes=limitation_notes,
        )

        warnings_list: List[str] = []
        if validation_errors:
            warnings_list.append(f"{len(validation_errors)} telemetry validation error(s) detected.")
        if failed_agents:
            warnings_list.append(f"Agent(s) failed during execution: {', '.join(failed_agents)}.")
        if timed_out_agents:
            warnings_list.append(f"Agent(s) timed out: {', '.join(timed_out_agents)}.")
        if rejected_messages:
            warnings_list.append(f"{len(rejected_messages)} agent message(s) rejected during validation.")
        if conflicting_evidence:
            warnings_list.append(f"{len(conflicting_evidence)} cross-agent telemetry contradiction(s) detected.")
        if stale_devices:
            warnings_list.append(f"Stale telemetry detected for device(s): {', '.join(stale_devices)}.")
        if final_confidence < 0.40:
            warnings_list.append("Low diagnostic confidence (< 0.40); root cause is provisional or indeterminate.")

        if baseline_findings:
            validated_findings.extend(baseline_findings)

        # Assemble unified DiagnosticReport (satisfying all Milestone 9 and 10 requirements)
        all_hypotheses = ([rc_candidate] if rc_candidate else []) + alt_causes
        now_utc = datetime.now(timezone.utc)

        report = DiagnosticReport(
            report_id=report_id,
            diagnosis_id=report_id,
            task_id=task_id,
            timestamp=now_utc,
            execution_timestamp=now_utc,
            schema_version="2.0.0",
            report_version="2.0.0",
            execution_duration_ms=duration_ms,
            overall_network_health=health_status,
            fault_detected=fault_detected_flag,
            confidence_interpretation="CALIBRATED_HEURISTIC_SCORE",
            overall_status=overall_status,
            execution_status=overall_status,
            probable_root_cause=rc_candidate,
            selected_root_cause=rc_candidate,
            alternative_causes=alt_causes,
            alternative_hypotheses=alt_causes,
            root_cause_hypotheses=all_hypotheses,
            affected_devices=list(affected_set),
            supporting_evidence=consolidated_evidence,
            individual_agent_findings=agent_messages,
            confidence_score=final_confidence,
            confidence=final_confidence,
            recommended_corrective_actions=actions,
            recommendations=actions,
            agent_execution_summary=agent_execution_summary,
            successful_agents=successful_agents,
            failed_agents=failed_agents,
            timed_out_agents=timed_out_agents,
            validated_findings=validated_findings,
            rejected_messages=rejected_messages,
            conflicting_evidence=conflicting_evidence,
            uncertainty_notes=uncertainty_notes,
            limitations=limitations,
            warnings=warnings_list,
            errors=errors,
            summary=summary,
        )

        if save_report:
            try:
                self._save_report(report)
            except Exception as save_err:
                self.logger.warning(f"Failed to persist report {report_id}: {save_err}")
                report.warnings.append(f"Report persistence warning: {str(save_err)}")

        self.logger.info(f"Diagnosis completed for task {task_id}. Report ID: {report_id} Status: {overall_status}")
        return report

    # -------------------------------------------------------------------------
    # CONTRADICTION & CONFLICT RESOLUTION
    # -------------------------------------------------------------------------

    def _detect_and_resolve_conflicts(
        self,
        agent_messages: Dict[str, AgentMessage],
        df: pd.DataFrame,
    ) -> Tuple[List[Dict[str, Any]], float, List[str], List[str]]:
        """
        Evidence-based conflict resolution comparing cross-agent findings and telemetry.
        Identifies contradictions explicitly, applies calibrated confidence adjustments,
        and documents uncertainty without fabricating evidence.
        Returns: (conflicts, confidence_penalty, uncertainty_notes, stale_devices)
        """
        conflicts: List[Dict[str, Any]] = []
        uncertainty_notes: List[str] = []
        stale_devices: List[str] = []
        total_penalty = 0.0

        perf_msg = agent_messages.get("performance_agent")
        infra_msg = agent_messages.get("infrastructure_agent")
        conn_msg = agent_messages.get("connectivity_agent")

        perf_findings = perf_msg.findings if perf_msg else []
        infra_findings = infra_msg.findings if infra_msg else []
        conn_findings = conn_msg.findings if conn_msg else []

        # Map findings by affected devices
        devices_with_perf_loss: Dict[str, Finding] = {}
        devices_with_perf_congestion: Dict[str, Finding] = {}
        for f in perf_findings:
            title_lower = f.title.lower()
            for dev in f.affected_devices:
                # Critical loss or latency
                if ("packet loss" in title_lower and f.severity in [Severity.CRITICAL, Severity.HIGH]) or ("latency" in title_lower and f.severity == Severity.CRITICAL):
                    devices_with_perf_loss[dev] = f
                if "bandwidth" in title_lower or "congestion" in title_lower:
                    devices_with_perf_congestion[dev] = f

        devices_with_infra_offline: Dict[str, Finding] = {}
        devices_with_infra_errors: Dict[str, Finding] = {}
        for f in infra_findings:
            title_lower = f.title.lower()
            for dev in f.affected_devices:
                if "offline" in title_lower or "down" in title_lower or "unreachable" in title_lower:
                    devices_with_infra_offline[dev] = f
                if "interface error" in title_lower or "crc" in title_lower or "drops" in title_lower:
                    devices_with_infra_errors[dev] = f

        devices_with_conn_healthy: Set[str] = set()
        devices_with_conn_failures: Set[str] = set()
        for f in conn_findings:
            if f.severity in [Severity.CRITICAL, Severity.HIGH, Severity.MEDIUM]:
                for dev in f.affected_devices:
                    devices_with_conn_failures.add(dev)

        # Check if genuine network transit congestion explains packet drops
        is_link_congested = False
        if "bandwidth_util_pct" in df.columns:
            is_link_congested = any(b >= 85.0 for b in df["bandwidth_util_pct"].dropna())
        if "queue_drops" in df.columns:
            is_link_congested = is_link_congested or any(q > 50 for q in df["queue_drops"].dropna())

        # Check all unique devices in telemetry
        telemetry_devices = set(df["device_id"].dropna().unique()) if "device_id" in df.columns else set()

        # Parse timestamps if present to detect stale telemetry
        batch_max_ts = None
        if "timestamp" in df.columns:
            try:
                ts_series = pd.to_datetime(df["timestamp"], format="mixed", utc=True, errors="coerce")
                if not ts_series.dropna().empty:
                    batch_max_ts = ts_series.max()
            except Exception:
                batch_max_ts = None

        for dev in telemetry_devices:
            dev_df = df[df["device_id"] == dev] if "device_id" in df.columns else pd.DataFrame()
            if not dev_df.empty:
                # Check for stale telemetry: if dev telemetry is significantly older than the batch,
                # historical presence alone does not prove current reachability.
                is_stale = False
                if batch_max_ts is not None and "timestamp" in dev_df.columns:
                    try:
                        dev_ts = pd.to_datetime(dev_df["timestamp"], format="mixed", utc=True, errors="coerce")
                        if not dev_ts.dropna().empty:
                            dev_max_ts = dev_ts.max()
                            # If device's latest telemetry is over 3 minutes older than the batch max, it is stale
                            if (batch_max_ts - dev_max_ts).total_seconds() > 180:
                                is_stale = True
                    except Exception:
                        pass

                if is_stale:
                    # Telemetry presence alone does not prove current reachability for stale devices
                    stale_devices.append(dev)
                    continue

                has_active_traffic = False
                if "connectivity_status" in dev_df.columns:
                    has_active_traffic = any(str(s).lower() == "connected" for s in dev_df["connectivity_status"])
                if "dns_resolution_status" in dev_df.columns:
                    has_active_traffic = has_active_traffic or any(str(s).lower() == "success" for s in dev_df["dns_resolution_status"])
                if has_active_traffic and dev not in devices_with_conn_failures:
                    devices_with_conn_healthy.add(dev)

        # ---------------------------------------------------------------------
        # CONTRADICTION A: High packet loss vs healthy reachability (unexplained by link congestion)
        # ---------------------------------------------------------------------
        if not is_link_congested:
            contradicted_loss_devs = [dev for dev in devices_with_perf_loss if dev in devices_with_conn_healthy]
            if contradicted_loss_devs:
                penalty = 0.10
                total_penalty += penalty
                conflict_record = {
                    "conflict_id": "CONF-A-PACKET-LOSS",
                    "type": "PACKET_LOSS_VS_HEALTHY_REACHABILITY",
                    "affected_devices": contradicted_loss_devs,
                    "agent_a": "performance_agent",
                    "finding_a": "Severe packet loss reported without link congestion",
                    "agent_b": "connectivity_agent",
                    "finding_b": "Active reachability and normal DNS resolution reported",
                    "resolution": "Hypothesis: Loss is isolated as localized transmission queuing or Wi-Fi RF drop rather than total transport reachability failure. Competing hypotheses preserved.",
                    "confidence_penalty": penalty,
                }
                conflicts.append(conflict_record)
                uncertainty_notes.append(
                    f"Contradiction on {contradicted_loss_devs}: performance_agent reports packet loss while connectivity_agent reports active reachability without link congestion. Confidence reduced by {penalty * 100:.1f}%."
                )

        # ---------------------------------------------------------------------
        # CONTRADICTION B: Offline device vs reachable device
        # ---------------------------------------------------------------------
        contradicted_offline_devs = [dev for dev in devices_with_infra_offline if dev in devices_with_conn_healthy]
        if contradicted_offline_devs:
            penalty = 0.15
            total_penalty += penalty
            conflict_record = {
                "conflict_id": "CONF-B-DEVICE-OFFLINE",
                "type": "DEVICE_OFFLINE_VS_REACHABLE",
                "affected_devices": contradicted_offline_devs,
                "agent_a": "infrastructure_agent",
                "finding_a": "Device reported offline or down",
                "agent_b": "connectivity_agent",
                "finding_b": "Device actively transmitting and reachable",
                "resolution": "Hypothesis: Device is actively transmitting in current window; infrastructure offline flag is likely a management agent heartbeat timeout or stale SNMP status. Competing hypotheses preserved.",
                "confidence_penalty": penalty,
            }
            conflicts.append(conflict_record)
            uncertainty_notes.append(
                f"Severe contradiction on {contradicted_offline_devs}: infrastructure_agent flagged device as offline, but connectivity telemetry confirms active communication. Confidence reduced by {penalty * 100:.1f}%."
            )

        # ---------------------------------------------------------------------
        # CONTRADICTION C: Performance congestion vs Physical interface errors
        # ---------------------------------------------------------------------
        conflict_c_devs = [dev for dev in devices_with_perf_congestion if dev in devices_with_infra_errors]
        if conflict_c_devs:
            penalty = 0.10
            total_penalty += penalty
            conflict_record = {
                "conflict_id": "CONF-C-CONGESTION-IFACE",
                "type": "CONGESTION_VS_PHYSICAL_FAILURE",
                "affected_devices": conflict_c_devs,
                "agent_a": "performance_agent",
                "finding_a": "Network congestion symptoms",
                "agent_b": "infrastructure_agent",
                "finding_b": "Physical interface errors and CRC framing corruption",
                "resolution": "Hypothesis: Physical CRC framing errors take precedence over pure traffic bandwidth congestion to prevent double-counting queue drops. Interface corruption is hypothesized as the primary fault driver.",
                "confidence_penalty": penalty,
            }
            conflicts.append(conflict_record)
            uncertainty_notes.append(
                f"Disambiguated on {conflict_c_devs}: congestion symptoms correlate with physical CRC framing errors. Physical layer failure prioritized over bandwidth upgrade."
            )

        return conflicts, min(0.35, total_penalty), uncertainty_notes, stale_devices

    # -------------------------------------------------------------------------
    # MESSAGE VALIDATION & INTEROPERABILITY
    # -------------------------------------------------------------------------

    def _validate_agent_message(
        self,
        raw_msg: Any,
        expected_agent_id: str,
        task_id: str,
        seen_message_ids: Set[str],
    ) -> Tuple[AgentMessage, Optional[Dict[str, Any]]]:
        """
        Validates incoming message against protocol schema, verifies agent identity,
        confidence boundaries, finding structures, and detects duplicate messages.
        Returns: (validated_agent_message, rejection_record_or_None)
        """
        if raw_msg is None:
            rejection = {
                "agent_id": expected_agent_id,
                "reason": "Agent returned null/None response.",
                "raw_message": "None",
            }
            return create_error_message(task_id, expected_agent_id, rejection["reason"]), rejection

        # Adapt or validate with protocol validator
        try:
            validated = validate_message(raw_msg)
        except Exception as exc:
            rejection = {
                "agent_id": expected_agent_id,
                "reason": f"AgentMessage schema validation failed: {str(exc)}",
                "raw_message": str(raw_msg)[:200],
            }
            return create_error_message(task_id, expected_agent_id, rejection["reason"]), rejection

        # Check agent identity
        if validated.agent_id != expected_agent_id:
            rejection = {
                "agent_id": expected_agent_id,
                "reason": f"Agent ID mismatch: expected '{expected_agent_id}', received '{validated.agent_id}'.",
                "raw_message": str(validated.message_id),
            }
            return create_error_message(task_id, expected_agent_id, rejection["reason"]), rejection

        # Check duplicate message
        if validated.message_id in seen_message_ids:
            rejection = {
                "agent_id": expected_agent_id,
                "reason": f"Duplicate message detected: message_id '{validated.message_id}' already processed.",
                "raw_message": str(validated.message_id),
            }
            return create_error_message(task_id, expected_agent_id, rejection["reason"]), rejection
        seen_message_ids.add(validated.message_id)

        # Check confidence boundary [0.0, 1.0] and finiteness
        import math
        conf_val = getattr(validated, "confidence", None)
        if (
            conf_val is None
            or not isinstance(conf_val, (int, float))
            or isinstance(conf_val, bool)
            or math.isnan(conf_val)
            or math.isinf(conf_val)
            or conf_val < 0.0
            or conf_val > 1.0
        ):
            rejection = {
                "agent_id": expected_agent_id,
                "reason": f"Confidence value invalid or out of bounds: {conf_val} (must be a finite numeric value between 0.0 and 1.0).",
                "raw_message": str(conf_val),
            }
            return create_error_message(task_id, expected_agent_id, rejection["reason"]), rejection

        return validated, None

    def _execute_agent_timed(self, agent: Any, task_id: str, df: pd.DataFrame) -> Tuple[Any, float]:
        """Executes an agent and measures execution time in milliseconds."""
        t0 = time.perf_counter()
        raw_result = self._execute_agent_safe(agent, task_id, df)
        duration_ms = round((time.perf_counter() - t0) * 1000, 1)
        return raw_result, duration_ms

    def _execute_agent_safe(self, agent: Any, task_id: str, df: pd.DataFrame) -> Any:
        """Invokes an agent's execute or analyze method safely."""
        if hasattr(agent, "execute"):
            return agent.execute(task_id, df)
        elif hasattr(agent, "analyze"):
            return agent.analyze(task_id, df)
        raise AttributeError(f"Agent {type(agent)} has neither execute nor analyze method.")

    # -------------------------------------------------------------------------
    # TELEMETRY NORMALIZATION & VALIDATION
    # -------------------------------------------------------------------------

    def validate_and_normalize_telemetry(
        self,
        telemetry: Any,
    ) -> Tuple[pd.DataFrame, List[str]]:
        """
        Validates incoming telemetry against Pydantic schema and returns clean DataFrame.
        Isolates invalid records without discarding valid records in partial failure cases.
        """
        validation_errors: List[str] = []

        if telemetry is None:
            return pd.DataFrame(), ["Telemetry input cannot be None."]

        records: List[Dict[str, Any]] = []

        if isinstance(telemetry, pd.DataFrame):
            if telemetry.empty:
                return pd.DataFrame(), ["Telemetry DataFrame is empty."]
            records = telemetry.to_dict(orient="records")
        elif isinstance(telemetry, TelemetryBatch):
            records = [r.model_dump() for r in telemetry.records]
        elif isinstance(telemetry, list):
            if not telemetry:
                return pd.DataFrame(), ["Telemetry list is empty."]
            for idx, item in enumerate(telemetry):
                if isinstance(item, NetworkTelemetryRecord):
                    records.append(item.model_dump())
                elif isinstance(item, dict):
                    records.append(item)
                else:
                    validation_errors.append(f"Row {idx}: Invalid item type {type(item)}")
        elif isinstance(telemetry, dict):
            if "records" in telemetry and isinstance(telemetry["records"], list):
                records = telemetry["records"]
            else:
                records = [telemetry]
        else:
            return pd.DataFrame(), [f"Unsupported telemetry format: {type(telemetry)}"]

        if not records:
            if not validation_errors:
                validation_errors.append("No record dictionaries extracted from telemetry input.")
            return pd.DataFrame(), validation_errors

        # Validate rows with Pydantic
        valid_rows: List[Dict[str, Any]] = []
        for idx, row in enumerate(records):
            try:
                if not isinstance(row, dict):
                    validation_errors.append(f"Record {idx}: Expected dictionary record, got {type(row).__name__}.")
                    continue
                if "device_id" not in row or not str(row["device_id"]).strip():
                    validation_errors.append(f"Record {idx}: Missing required 'device_id'.")
                    continue
                # Sanitize NaN/Inf and pandas NA values to None so optional fields validate cleanly
                cleaned_row = {
                    k: (None if (isinstance(v, float) and (math.isnan(v) or math.isinf(v))) or pd.isna(v) else v)
                    for k, v in row.items()
                }
                validated_rec = NetworkTelemetryRecord.model_validate(cleaned_row)
                valid_rows.append(validated_rec.model_dump())
            except ValidationError as err:
                validation_errors.append(f"Record {idx} validation failure: {str(err).splitlines()[0]}")
            except Exception as exc:
                validation_errors.append(f"Record {idx} error: {str(exc)}")

        if not valid_rows:
            return pd.DataFrame(), validation_errors

        df = pd.DataFrame(valid_rows)
        return df, validation_errors

    def _save_report(self, report: DiagnosticReport) -> Path:
        """Saves JSON report to reports/ directory."""
        file_path = self.reports_dir / f"{report.report_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(report.model_dump_json(indent=2))
        return file_path
