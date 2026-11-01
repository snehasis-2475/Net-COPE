from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import uuid

import numpy as np

from communication.models import (
    AgentMessage,
    AgentStatus,
    EvidenceItem,
    Finding,
    Severity,
)
from communication.protocol import create_agent_message, validate_message
from diagnosis.models import (
    CorrelationConfig,
    CorrelationHypothesis,
    CorrelationResponse,
    NetworkHealthStatus,
    RootCauseCandidate,
)

logger = logging.getLogger("agent.correlation_agent")


class FaultCorrelationAgent:
    """
    Upgraded, evidence-based Multi-Agent Fault Correlation & Causal Inference Specialist.
    Synthesizes findings from Performance, Infrastructure, and Connectivity agents.
    Performs device-level grouping, cross-agent evidence aggregation, conflict resolution,
    and calculates evidence-backed root causes with calibrated confidence scores.
    """

    def __init__(self, config: Optional[CorrelationConfig] = None):
        self.agent_id = "correlation_agent"
        self.name = "Fault Correlation & Causal Inference Specialist"
        self.config = config or CorrelationConfig()

    # -------------------------------------------------------------------------
    # MAIN CORRELATION ENTRYPOINTS
    # -------------------------------------------------------------------------

    def correlate(
        self,
        task_id: str,
        agent_messages: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentMessage:
        """
        Primary interface matching orchestrator and existing test suite expectations.
        Accepts dictionary of agent messages, correlates evidence, and returns an AgentMessage.
        """
        response = self.analyze(task_id=task_id, agent_messages=agent_messages, context=context)
        return response.to_agent_message()

    def analyze(
        self,
        task_id: str,
        agent_messages: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> CorrelationResponse:
        """
        Structured analysis interface producing a CorrelationResponse object.
        """
        context = context or {}
        active_config = context.get("config", self.config)
        if isinstance(active_config, dict):
            active_config = CorrelationConfig.model_validate(active_config)

        errors: List[str] = []

        # 1. Normalize and extract structured inputs
        normalized_messages = self._normalize_agent_inputs(agent_messages, errors)

        active_agents = list(normalized_messages.values())
        if not active_agents:
            insuff_hyp = CorrelationHypothesis(
                hypothesis_id=f"HYP-INSUFF-{uuid.uuid4().hex[:6].upper()}",
                title="Insufficient Telemetry / Agent Data",
                probable_root_cause="Insufficient Telemetry / Agent Data",
                category="INDETERMINATE",
                description="No specialized diagnostic agents provided usable telemetry findings.",
                severity="warning",
                confidence=0.10,
                supporting_findings=[],
                supporting_agents=[],
                evidence=[],
                uncertainty_explanation="All specialized agents were missing, timed out, or returned empty results.",
                recommended_investigation="Verify agent service availability and check telemetry stream integrity.",
            )
            finding = Finding(
                category="CORRELATION",
                title="Insufficient Telemetry / Agent Data",
                description="No specialized agents provided usable telemetry findings.",
                severity=Severity.HIGH,
            )
            return CorrelationResponse(
                agent_id=self.agent_id,
                task_id=task_id,
                status=AgentStatus.INSUFFICIENT_DATA,
                timestamp=datetime.now(timezone.utc),
                overall_health=NetworkHealthStatus.UNKNOWN,
                primary_hypothesis=insuff_hyp,
                alternative_hypotheses=[],
                findings=[finding],
                evidence=[],
                confidence=0.10,
                errors=["No specialized agent responses available for correlation."] + errors,
                metadata={"root_cause": "INSUFFICIENT_EVIDENCE"},
            )

        # 2. Collect, de-duplicate, and filter findings and evidence
        all_findings, all_evidence, affected_devices = self._aggregate_findings_and_evidence(
            normalized_messages=normalized_messages,
            config=active_config,
            errors=errors,
        )

        # 3. Check if all agents report nominal health
        if not all_findings:
            nominal_hyp = CorrelationHypothesis(
                hypothesis_id=f"HYP-NOMINAL-{uuid.uuid4().hex[:6].upper()}",
                title="Nominal Network Operation",
                probable_root_cause="Nominal Network Operation",
                category="NOMINAL",
                description="Network is operating within designated SLA parameters. No anomalous metrics detected across any agent domain.",
                severity="info",
                confidence=0.98,
                supporting_findings=["All specialized agents reported normal thresholds."],
                supporting_agents=list(normalized_messages.keys()),
                evidence=[e.details or f"{e.metric_name}: {e.observed_value}" for e in all_evidence],
                evidence_references=[e.metric_name for e in all_evidence],
                affected_devices=list(affected_devices),
                uncertainty_explanation="High diagnostic certainty; all telemetry is nominal.",
                recommended_investigation="Continue standard monitoring baseline.",
            )
            nominal_finding = Finding(
                category="CORRELATION",
                title="Nominal Network Operation",
                description="Cross-agent telemetry correlation indicates zero significant anomalies across performance, infrastructure, and connectivity domains.",
                severity=Severity.INFO,
                affected_devices=list(affected_devices),
                metrics={"active_agents": len(active_agents)},
            )
            return CorrelationResponse(
                agent_id=self.agent_id,
                task_id=task_id,
                status=AgentStatus.SUCCESS,
                timestamp=datetime.now(timezone.utc),
                overall_health=NetworkHealthStatus.HEALTHY,
                primary_hypothesis=nominal_hyp,
                alternative_hypotheses=[],
                findings=[nominal_finding],
                evidence=all_evidence,
                confidence=0.98,
                errors=errors,
                metadata={
                    "probable_root_cause": nominal_hyp.model_dump(),
                    "alternative_causes": [],
                    "health_status": NetworkHealthStatus.HEALTHY.value,
                },
            )

        # 4. Formulate and score causal hypotheses against cross-agent rules
        candidates = self._evaluate_hypotheses(
            findings=all_findings,
            evidence=all_evidence,
            affected_devices=list(affected_devices),
            active_agents=normalized_messages,
            config=active_config,
        )

        # 5. Handle insufficient or conflicting evidence
        if not candidates or candidates[0].confidence < active_config.min_confidence_threshold:
            indeterminate_hyp = self._build_indeterminate_hypothesis(
                all_findings=all_findings,
                all_evidence=all_evidence,
                affected_devices=list(affected_devices),
                candidates=candidates,
            )
            indet_finding = Finding(
                category="CORRELATION",
                title=f"Root Cause: {indeterminate_hyp.title}",
                description=indeterminate_hyp.description,
                severity=Severity.MEDIUM,
                affected_devices=list(affected_devices),
            )
            return CorrelationResponse(
                agent_id=self.agent_id,
                task_id=task_id,
                status=AgentStatus.WARNING,
                timestamp=datetime.now(timezone.utc),
                overall_health=NetworkHealthStatus.DEGRADED,
                primary_hypothesis=indeterminate_hyp,
                alternative_hypotheses=candidates,
                findings=[indet_finding] + all_findings,
                evidence=all_evidence,
                confidence=indeterminate_hyp.confidence,
                errors=errors,
                metadata={
                    "probable_root_cause": indeterminate_hyp.model_dump(),
                    "alternative_causes": [c.model_dump() for c in candidates],
                    "health_status": NetworkHealthStatus.DEGRADED.value,
                },
            )

        primary_candidate = candidates[0]
        alternative_candidates = candidates[1:4]

        # 6. Resolve multi-hypothesis uncertainty if two hypotheses are very close
        if len(candidates) >= 2:
            second_candidate = candidates[1]
            if (primary_candidate.confidence - second_candidate.confidence) <= 0.12:
                primary_candidate.uncertainty_explanation = (
                    f"Two plausible root causes identified: '{primary_candidate.title}' ({primary_candidate.confidence:.2f}) "
                    f"and '{second_candidate.title}' ({second_candidate.confidence:.2f}). "
                    "Current evidence exhibits overlapping symptoms; operator verification recommended."
                )
                primary_candidate.alternative_hypotheses.append(second_candidate.title)

        # 7. Overall health assessment
        has_critical = any(f.severity == Severity.CRITICAL for f in all_findings) or primary_candidate.severity == "critical"
        if has_critical or primary_candidate.confidence >= active_config.high_confidence_threshold:
            health_status = NetworkHealthStatus.CRITICAL
        else:
            health_status = NetworkHealthStatus.DEGRADED

        corr_finding_sev = Severity.CRITICAL if health_status == NetworkHealthStatus.CRITICAL else Severity.HIGH
        correlation_finding = Finding(
            category="CORRELATION",
            title=f"Root Cause: {primary_candidate.title}",
            description=primary_candidate.description,
            severity=corr_finding_sev,
            affected_devices=primary_candidate.affected_devices,
            metrics={
                "confidence": primary_candidate.confidence,
                "competing_hypotheses": len(alternative_candidates),
                "supporting_agents": primary_candidate.supporting_agents,
            },
        )

        return CorrelationResponse(
            agent_id=self.agent_id,
            task_id=task_id,
            status=AgentStatus.SUCCESS,
            timestamp=datetime.now(timezone.utc),
            overall_health=health_status,
            primary_hypothesis=primary_candidate,
            alternative_hypotheses=alternative_candidates,
            findings=[correlation_finding] + all_findings,
            evidence=all_evidence,
            confidence=primary_candidate.confidence,
            errors=errors,
            metadata={
                "probable_root_cause": primary_candidate.model_dump(),
                "alternative_causes": [c.model_dump() for c in alternative_candidates],
                "health_status": health_status.value,
            },
        )

    # -------------------------------------------------------------------------
    # HYPOTHESIS EVALUATION RULES
    # -------------------------------------------------------------------------

    def _evaluate_hypotheses(
        self,
        findings: List[Finding],
        evidence: List[EvidenceItem],
        affected_devices: List[str],
        active_agents: Dict[str, AgentMessage],
        config: CorrelationConfig,
    ) -> List[CorrelationHypothesis]:
        """
        Evaluates cross-agent causal correlation rules across scenarios A through F.
        Distinguishes observed evidence from inferred causes and prevents artificial confidence inflation.
        """
        finding_texts = " ".join([f.title.lower() + " " + f.description.lower() for f in findings])
        evidence_metrics = {e.metric_name: e for e in evidence}

        candidates: List[CorrelationHypothesis] = []

        # =====================================================================
        # SCENARIO A: Network Congestion & Bufferbloat
        # =====================================================================
        has_bw_sat = any(k in evidence_metrics for k in ["bandwidth_util_pct", "bandwidth_utilization_percent"]) or "bandwidth" in finding_texts
        has_queue_drops = "queue_drops" in evidence_metrics or "queue drops" in finding_texts
        has_latency = any(k in evidence_metrics for k in ["latency_ms", "jitter_ms"]) or "latency" in finding_texts or "jitter" in finding_texts
        has_loss = any(k in evidence_metrics for k in ["packet_loss_pct", "packet_loss_percent"]) or "packet loss" in finding_texts
        has_cpu_overload = any(k in evidence_metrics for k in ["cpu_util_pct", "cpu_utilization_percent"]) or "cpu overload" in finding_texts or "critical cpu" in finding_texts

        if has_bw_sat or (has_queue_drops and has_latency):
            score = 0.50
            supporting_findings = []
            supporting_agents: Set[str] = set()
            observed_evidence = []
            contradicting = []

            if has_bw_sat:
                score += 0.25
                supporting_findings.append("Link bandwidth utilization exceeded operational thresholds.")
                observed_evidence.append("High bandwidth consumption.")
            if has_queue_drops:
                score += 0.15
                supporting_findings.append("Hardware queue drops observed due to buffer saturation.")
                observed_evidence.append("Hardware buffer tail drops.")
            if has_latency:
                score += 0.10
                supporting_findings.append("Elevated bufferbloat and RTT queuing delay.")
                observed_evidence.append("Increased latency and jitter.")
            if has_loss:
                score += 0.05
                supporting_findings.append("TCP packet transmission loss correlating with congestion.")

            # Identify contributing agents
            for ag_name, ag_msg in active_agents.items():
                if any("bandwidth" in f.title.lower() or "latency" in f.title.lower() or "queue" in f.title.lower() for f in ag_msg.findings):
                    supporting_agents.add(ag_name)

            if len(supporting_agents) >= 2:
                score += config.multi_agent_boost

            # Contradiction: Pegged CPU indicates compute bottleneck rather than pure transit congestion
            if has_cpu_overload:
                score -= config.conflict_penalty
                contradicting.append("Control plane CPU is pegged, indicating compute overload rather than pure link transit congestion.")

            confidence = min(0.98, max(0.10, round(score, 2)))
            candidates.append(
                CorrelationHypothesis(
                    hypothesis_id=f"HYP-CONGEST-{uuid.uuid4().hex[:6].upper()}",
                    title="Network Bandwidth Congestion & Bufferbloat",
                    probable_root_cause="Network Bandwidth Congestion & Bufferbloat",
                    category="PERFORMANCE",
                    description="Traffic volume exceeded interface transmission capacity, filling switch buffers and causing tail drops, jitter, and latency spikes.",
                    severity="critical" if confidence >= 0.85 else "warning",
                    confidence=confidence,
                    affected_devices=affected_devices,
                    supporting_findings=supporting_findings,
                    supporting_agents=list(supporting_agents),
                    evidence=observed_evidence,
                    evidence_references=[m for m in ["bandwidth_utilization_percent", "bandwidth_util_pct", "queue_drops", "latency_ms", "packet_loss_percent"] if m in evidence_metrics],
                    supporting_symptoms=supporting_findings,
                    contradicting_symptoms=contradicting,
                    probable_impact="TCP throughput collapse, video conferencing freezes, and interactive RPC timeouts.",
                    recommended_investigation="Inspect NetFlow/sFlow top talkers, verify QoS queue allocations, and consider interface bandwidth upgrade.",
                )
            )

        # =====================================================================
        # SCENARIO B: Infrastructure / Compute Resource Overload
        # =====================================================================
        has_mem_pressure = any(k in evidence_metrics for k in ["memory_util_pct", "memory_utilization_percent"]) or "memory pressure" in finding_texts or "memory utilization" in finding_texts

        if has_cpu_overload or has_mem_pressure:
            score = 0.55
            supporting_findings = []
            supporting_agents = set()
            observed_evidence = []
            contradicting = []

            if has_cpu_overload:
                score += 0.30
                supporting_findings.append("Control plane CPU spiked into critical saturation range.")
                observed_evidence.append("Peak CPU utilization exceeded safe limits.")
            if has_mem_pressure:
                score += 0.15
                supporting_findings.append("System memory exhausted or high RAM utilization.")
                observed_evidence.append("High RAM consumption.")
            if has_queue_drops:
                score += 0.05
                supporting_findings.append("Process-level queue drops due to delayed scheduler handling.")
                observed_evidence.append("Packet queue tail drops.")
            if has_loss or has_latency:
                score += 0.05
                supporting_findings.append("Transit packet delays secondary to compute exhaustion.")

            for ag_name, ag_msg in active_agents.items():
                if any("cpu" in f.title.lower() or "memory" in f.title.lower() for f in ag_msg.findings):
                    supporting_agents.add(ag_name)

            if len(supporting_agents) >= 2:
                score += config.multi_agent_boost

            confidence = min(0.98, max(0.10, round(score, 2)))
            candidates.append(
                CorrelationHypothesis(
                    hypothesis_id=f"HYP-INFRA-{uuid.uuid4().hex[:6].upper()}",
                    title="Device Hardware / Compute Resource Overload",
                    probable_root_cause="Device Hardware / Compute Resource Overload",
                    category="INFRASTRUCTURE",
                    description="Network appliance CPU/Memory exhaustion preventing timely routing, packet inspection, or packet forwarding.",
                    severity="critical" if confidence >= 0.85 else "warning",
                    confidence=confidence,
                    affected_devices=affected_devices,
                    supporting_findings=supporting_findings,
                    supporting_agents=list(supporting_agents),
                    evidence=observed_evidence,
                    evidence_references=[m for m in ["cpu_utilization_percent", "cpu_util_pct", "memory_utilization_percent", "memory_util_pct", "queue_drops"] if m in evidence_metrics],
                    supporting_symptoms=supporting_findings,
                    contradicting_symptoms=contradicting,
                    probable_impact="Control plane unresponsiveness, routing protocol keepalive drops (BGP/OSPF flaps), and dropped transit packets.",
                    recommended_investigation="Identify rogue processes (show processes cpu/memory), inspect control plane ACLs, and evaluate firmware memory leaks.",
                )
            )

        # =====================================================================
        # SCENARIO C: DNS Service Degradation
        # =====================================================================
        has_dns_fail = any(k in evidence_metrics for k in ["dns_resolution_status", "dns_status"]) or "dns resolution failure" in finding_texts
        has_dns_lat = "dns_latency_ms" in evidence_metrics or "dns response time" in finding_texts or "dns query delay" in finding_texts
        has_iface_down = "interface_status" in evidence_metrics or "interface physical" in finding_texts or "link disconnected" in finding_texts

        if has_dns_fail or has_dns_lat:
            score = 0.55
            supporting_findings = []
            supporting_agents = set()
            observed_evidence = []
            contradicting = []

            if has_dns_fail:
                score += 0.35
                supporting_findings.append("DNS queries returned timeout, servfail, or refused errors.")
                observed_evidence.append("DNS query resolution failures.")
            if has_dns_lat:
                score += 0.10
                supporting_findings.append("Severe DNS resolution delay observed.")
                observed_evidence.append("Elevated DNS lookup latency.")

            # Independent verification: Underlying IP link is healthy
            if not has_loss and not has_iface_down:
                score += 0.05
                supporting_findings.append("Underlying IP link layer is healthy; fault is isolated to naming service layer.")
            elif has_iface_down:
                score -= config.conflict_penalty
                contradicting.append("Physical link is down, which explains upstream DNS query failures.")

            for ag_name, ag_msg in active_agents.items():
                if any("dns" in f.title.lower() for f in ag_msg.findings):
                    supporting_agents.add(ag_name)

            if len(supporting_agents) >= 2:
                score += config.multi_agent_boost

            confidence = min(0.99, max(0.10, round(score, 2)))
            candidates.append(
                CorrelationHypothesis(
                    hypothesis_id=f"HYP-DNS-{uuid.uuid4().hex[:6].upper()}",
                    title="DNS Resolver Outage or Misconfiguration",
                    probable_root_cause="DNS Resolver Outage or Misconfiguration",
                    category="CONNECTIVITY",
                    description="Upstream DNS forwarders, local resolver daemon, or firewall ACLs blocking UDP/TCP port 53 traffic.",
                    severity="critical" if confidence >= 0.85 else "warning",
                    confidence=confidence,
                    affected_devices=affected_devices,
                    supporting_findings=supporting_findings,
                    supporting_agents=list(supporting_agents),
                    evidence=observed_evidence,
                    evidence_references=[m for m in ["dns_status", "dns_resolution_status", "dns_latency_ms"] if m in evidence_metrics],
                    supporting_symptoms=supporting_findings,
                    contradicting_symptoms=contradicting,
                    probable_impact="Endpoints cannot resolve internal or external domain names, breaking web browsing, API calls, and email.",
                    recommended_investigation="Verify DNS server reachability, test local resolver port 53 listener, and check DNS forwarder server status.",
                )
            )

        # =====================================================================
        # SCENARIO D: Wireless RF Degradation (Weak Wi-Fi)
        # =====================================================================
        has_wifi_weak = any(k in evidence_metrics for k in ["wifi_rssi_dbm", "wifi_signal_dbm"]) or "weak wi-fi" in finding_texts or "wireless signal" in finding_texts

        if has_wifi_weak:
            score = 0.55
            supporting_findings = []
            supporting_agents = set()
            observed_evidence = []
            contradicting = []

            score += 0.35
            supporting_findings.append("Wi-Fi RSSI degraded below acceptable coverage limits and/or SNR degraded.")
            observed_evidence.append("Weak wireless RSSI signal power.")
            if has_loss:
                score += 0.10
                supporting_findings.append("Associated frame drops due to RF multipath fading or distance.")
                observed_evidence.append("Packet loss over wireless link.")
            if not has_bw_sat and not has_cpu_overload:
                score += 0.05
                supporting_findings.append("Core network infrastructure and link bandwidth are healthy; fault is isolated to 802.11 wireless medium.")

            for ag_name, ag_msg in active_agents.items():
                if any("wi-fi" in f.title.lower() or "wireless" in f.title.lower() for f in ag_msg.findings):
                    supporting_agents.add(ag_name)

            if len(supporting_agents) >= 2:
                score += config.multi_agent_boost

            confidence = min(0.99, max(0.10, round(score, 2)))
            candidates.append(
                CorrelationHypothesis(
                    hypothesis_id=f"HYP-WIFI-{uuid.uuid4().hex[:6].upper()}",
                    title="Wireless RF Attenuation / Weak Wi-Fi Coverage",
                    probable_root_cause="Wireless RF Attenuation / Weak Wi-Fi Coverage",
                    category="CONNECTIVITY",
                    description="Client device is located in an RF coverage dead-zone, experiencing high attenuation, or suffering co-channel interference.",
                    severity="critical" if confidence >= 0.85 else "warning",
                    confidence=confidence,
                    affected_devices=affected_devices,
                    supporting_findings=supporting_findings,
                    supporting_agents=list(supporting_agents),
                    evidence=observed_evidence,
                    evidence_references=[m for m in ["wifi_signal_dbm", "wifi_rssi_dbm", "wifi_snr_db", "packet_loss_percent", "packet_loss_pct"] if m in evidence_metrics],
                    supporting_symptoms=supporting_findings,
                    contradicting_symptoms=contradicting,
                    probable_impact="Wireless clients experience degraded throughput, VoIP audio distortion, and intermittent Wi-Fi drops.",
                    recommended_investigation="Perform Wi-Fi heatmapping survey, inspect AP antenna alignment, and check 2.4/5GHz channel overlap.",
                )
            )

        # =====================================================================
        # SCENARIO E: Physical Interface / Cable Failure
        # =====================================================================
        has_crc_errors = "interface_errors" in evidence_metrics or "crc errors" in finding_texts or "frame / crc" in finding_texts

        if has_iface_down or has_crc_errors:
            score = 0.50
            supporting_findings = []
            supporting_agents = set()
            observed_evidence = []
            contradicting = []

            if has_iface_down:
                score += 0.35
                supporting_findings.append("Physical interface state reported down or flapping.")
                observed_evidence.append("Physical link down / flapping state.")
            if has_crc_errors:
                score += 0.15
                supporting_findings.append("High interface CRC / framing errors detected.")
                observed_evidence.append("Cumulative CRC / FCS error counter breaches.")
            if has_loss:
                score += 0.05
                supporting_findings.append("Associated packet transmission loss.")

            # Contradiction: If this is purely a wireless weak RSSI issue, wired cable fault is contradicted
            if has_wifi_weak and not has_crc_errors:
                score -= config.conflict_penalty
                contradicting.append("Wi-Fi signal degradation also reported; may be wireless link instead of wired port.")

            for ag_name, ag_msg in active_agents.items():
                if any("interface" in f.title.lower() or "cable" in f.title.lower() or "crc" in f.title.lower() for f in ag_msg.findings):
                    supporting_agents.add(ag_name)

            if len(supporting_agents) >= 2:
                score += config.multi_agent_boost

            confidence = min(0.99, max(0.10, round(score, 2)))
            candidates.append(
                CorrelationHypothesis(
                    hypothesis_id=f"HYP-IFACE-{uuid.uuid4().hex[:6].upper()}",
                    title="Physical Interface / Cable Failure",
                    probable_root_cause="Physical Interface / Cable Failure",
                    category="INFRASTRUCTURE",
                    description="Physical link flapping, transceiver fault (SFP), bad patch cable, or port shutdown causing link layer disconnection.",
                    severity="critical" if confidence >= 0.85 else "warning",
                    confidence=confidence,
                    affected_devices=affected_devices,
                    supporting_findings=supporting_findings,
                    supporting_agents=list(supporting_agents),
                    evidence=observed_evidence,
                    evidence_references=[m for m in ["interface_status", "interface_errors", "packet_loss_percent", "packet_loss_pct"] if m in evidence_metrics],
                    supporting_symptoms=supporting_findings,
                    contradicting_symptoms=contradicting,
                    probable_impact="Total layer 2/3 traffic partition through the failed physical interface.",
                    recommended_investigation="Replace patch cable, verify optical transceiver light levels (show interfaces transceiver), and inspect switchport.",
                )
            )

        # =====================================================================
        # SCENARIO F: DHCP Service Failure / Scope Exhaustion
        # =====================================================================
        has_dhcp_fail = "dhcp_status" in evidence_metrics or "dhcp pool exhaustion" in finding_texts or "dhcp allocation failure" in finding_texts

        if has_dhcp_fail:
            score = 0.60
            supporting_findings = []
            supporting_agents = set()
            observed_evidence = []
            contradicting = []

            score += 0.35
            supporting_findings.append("DHCP assignment timeout, pool exhaustion, or NACK observed.")
            observed_evidence.append("DHCP lease acquisition failure.")
            if not has_iface_down:
                score += 0.05
                supporting_findings.append("Local link is connected but client cannot obtain valid IPv4 lease.")
            else:
                score -= config.conflict_penalty
                contradicting.append("Interface is down, which prevents DHCP broadcast packet transmission.")

            for ag_name, ag_msg in active_agents.items():
                if any("dhcp" in f.title.lower() for f in ag_msg.findings):
                    supporting_agents.add(ag_name)

            if len(supporting_agents) >= 2:
                score += config.multi_agent_boost

            confidence = min(0.99, max(0.10, round(score, 2)))
            candidates.append(
                CorrelationHypothesis(
                    hypothesis_id=f"HYP-DHCP-{uuid.uuid4().hex[:6].upper()}",
                    title="DHCP Service Failure / Scope Exhaustion",
                    probable_root_cause="DHCP Service Failure / Scope Exhaustion",
                    category="CONNECTIVITY",
                    description="DHCP scope addresses exhausted, DHCP relay agent misconfigured, or DHCP server daemon unresponsive.",
                    severity="critical" if confidence >= 0.85 else "warning",
                    confidence=confidence,
                    affected_devices=affected_devices,
                    supporting_findings=supporting_findings,
                    supporting_agents=list(supporting_agents),
                    evidence=observed_evidence,
                    evidence_references=[m for m in ["dhcp_status"] if m in evidence_metrics],
                    supporting_symptoms=supporting_findings,
                    contradicting_symptoms=contradicting,
                    probable_impact="New endpoints cannot obtain IP addresses and fall back to 169.254.x.x link-local addressing.",
                    recommended_investigation="Check DHCP server scope statistics for free IPs, verify ip helper-address on default gateway, and restart DHCP service.",
                )
            )

        # =====================================================================
        # SCENARIO H: Rolling Baseline Anomaly / Silent Degradation
        # =====================================================================
        baseline_findings = [f for f in findings if getattr(f, "source_agent", None) == "baseline_detector" or "baseline anomaly" in f.title.lower()]
        if baseline_findings:
            base_devs = list({dev for f in baseline_findings for dev in f.affected_devices if dev})
            base_ev_texts = [e.details for e in evidence if e.details and "rolling baseline" in e.details]
            if not base_ev_texts:
                base_ev_texts = [f.description for f in baseline_findings]

            has_confirmed_rule = any(c.confidence >= 0.80 and not c.hypothesis_id.startswith("HYP-BASELINE") for c in candidates)

            if has_confirmed_rule:
                for c in candidates:
                    if c.confidence >= 0.80:
                        c.evidence.extend(base_ev_texts[:2])
                        c.supporting_symptoms.append("Corroborated by rolling baseline statistical anomaly detector.")
            else:
                candidates.append(
                    CorrelationHypothesis(
                        hypothesis_id=f"HYP-BASELINE-{uuid.uuid4().hex[:6].upper()}",
                        title="Silent Performance Degradation (Rolling Baseline Drift)",
                        probable_root_cause="Silent Performance Degradation (Rolling Baseline Drift)",
                        category="DEGRADED",
                        description=(
                            f"Statistical baseline anomaly detected across {len(base_devs)} device(s): "
                            f"{baseline_findings[0].description}"
                        ),
                        severity="warning",
                        confidence=0.55,
                        affected_devices=base_devs or affected_devices,
                        supporting_findings=[f.title for f in baseline_findings],
                        supporting_agents=["baseline_detector"],
                        evidence=base_ev_texts[:5],
                        uncertainty_explanation=(
                            "Metrics show sustained statistical deviation from historical baseline without crossing "
                            "static threshold limits. Operator verification advised."
                        ),
                        recommended_investigation=(
                            "Inspect device telemetry trends, recent configuration changes, and background workload "
                            "growth causing baseline drift."
                        ),
                    )
                )

        # Sort descending by calibrated confidence
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates

    # -------------------------------------------------------------------------
    # INDETERMINATE HYPOTHESIS & HELPER METHODS
    # -------------------------------------------------------------------------

    def _build_indeterminate_hypothesis(
        self,
        all_findings: List[Finding],
        all_evidence: List[EvidenceItem],
        affected_devices: List[str],
        candidates: List[CorrelationHypothesis],
    ) -> CorrelationHypothesis:
        competing = [c.title for c in candidates[:3]]
        return CorrelationHypothesis(
            hypothesis_id=f"HYP-INDET-{uuid.uuid4().hex[:6].upper()}",
            title="Indeterminate Root Cause (Insufficient Evidence)",
            probable_root_cause="Indeterminate Root Cause (Insufficient Evidence)",
            category="INDETERMINATE",
            description=(
                "Anomalous telemetry signals were observed, but symptoms do not conclusively match known fault patterns. "
                "Available evidence is sparse, isolated to a single weak metric, or contradictory across domains."
            ),
            severity="warning",
            confidence=0.30,
            affected_devices=affected_devices,
            supporting_findings=[f.title for f in all_findings],
            supporting_agents=[],
            evidence=[e.details or f"{e.metric_name}: {e.observed_value}" for e in all_evidence],
            evidence_references=[e.metric_name for e in all_evidence],
            supporting_symptoms=[f.title for f in all_findings],
            contradicting_symptoms=["Lack of definitive corroborating telemetry across complementary agents."],
            alternative_hypotheses=competing,
            uncertainty_explanation=(
                f"Observed signals lacked multi-agent corroboration. Competing potential explanations: {', '.join(competing) if competing else 'None'}."
            ),
            probable_impact="Potential localized impairment; full blast radius unknown without further telemetry.",
            recommended_investigation="Deploy targeted packet capture (tcpdump/Wireshark) and increase telemetry polling frequency.",
        )

    def _normalize_agent_inputs(
        self,
        raw_inputs: Dict[str, Any],
        errors: List[str],
    ) -> Dict[str, AgentMessage]:
        normalized: Dict[str, AgentMessage] = {}
        for agent_name, raw_obj in raw_inputs.items():
            if raw_obj is None:
                continue
            try:
                msg = validate_message(raw_obj)
                normalized[agent_name] = msg
            except Exception as exc:
                err = f"Failed to normalize message from agent '{agent_name}': {exc}"
                logger.warning(err)
                errors.append(err)
        return normalized

    def _aggregate_findings_and_evidence(
        self,
        normalized_messages: Dict[str, AgentMessage],
        config: CorrelationConfig,
        errors: List[str],
    ) -> Tuple[List[Finding], List[EvidenceItem], Set[str]]:
        all_findings: List[Finding] = []
        all_evidence: List[EvidenceItem] = []
        affected_devices: Set[str] = set()

        seen_finding_signatures: Set[Tuple[str, str, str]] = set()
        seen_evidence_signatures: Set[Tuple[str, Optional[str]]] = set()

        # Track timestamps for time-window verification
        finding_timestamps: List[datetime] = []

        for agent_name, msg in normalized_messages.items():
            if msg.errors:
                errors.extend(msg.errors)

            for f in msg.findings:
                # Filter out informational nominal messages
                if f.severity == Severity.INFO and "healthy" in f.title.lower() or "nominal" in f.title.lower():
                    continue

                sig = (f.category, f.title, ",".join(sorted(f.affected_devices)))
                if sig in seen_finding_signatures:
                    continue  # Deduplicate duplicate findings across polls
                seen_finding_signatures.add(sig)

                all_findings.append(f)
                affected_devices.update(f.affected_devices)

            for e in msg.evidence:
                dev = getattr(e, "device_id", None)
                e_sig = (e.metric_name, dev)
                if e_sig in seen_evidence_signatures:
                    continue
                seen_evidence_signatures.add(e_sig)
                all_evidence.append(e)

        return all_findings, all_evidence, affected_devices
