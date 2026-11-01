from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional, Set, Union
import uuid

from communication.models import (
    AgentMessage,
    AgentStatus,
    EvidenceItem,
    Finding,
    Severity,
)
from communication.protocol import create_agent_message, validate_message
from diagnosis.models import (
    ActionPriority,
    ActionType,
    CorrectiveAction,
    ExecutionRisk,
    RecommendationAgentResponse,
    RecommendationItem,
    RootCauseCandidate,
)

logger = logging.getLogger("agent.recommendation_agent")


class RecommendationAgent:
    """
    Evidence-Based Network Remediation & Recommendation Agent.
    Converts correlated root-cause hypotheses and diagnostic evidence into prioritized,
    actionable, technically accurate remediation plans with explicit safety safeguards.
    """

    def __init__(self):
        self.agent_id = "recommendation_agent"
        self.name = "Remediation & Recommendation Specialist"

    # -------------------------------------------------------------------------
    # MAIN AGENT INTERFACES
    # -------------------------------------------------------------------------

    def recommend(
        self,
        task_id: str,
        correlation_message: Union[AgentMessage, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentMessage:
        """
        Primary execution method compatible with Central Orchestrator and existing tests.
        Returns an AgentMessage with metadata containing prioritized actions.
        """
        response = self.generate_recommendations(
            task_id=task_id,
            correlation_input=correlation_message,
            context=context,
        )
        return response.to_agent_message()

    def generate_recommendations(
        self,
        task_id: str,
        correlation_input: Any,
        context: Optional[Dict[str, Any]] = None,
    ) -> RecommendationAgentResponse:
        """
        Structured recommendation generation interface returning RecommendationAgentResponse.
        """
        context = context or {}
        errors: List[str] = []

        # 1. Extract and validate correlation components
        rc_candidate, alt_candidates, evidence_items, correlation_conf = self._extract_correlation_data(
            correlation_input=correlation_input,
            errors=errors,
        )

        recommendations: List[RecommendationItem] = []

        # 2. Generate actions based on root cause or lack thereof
        if not rc_candidate or correlation_conf < 0.35 or "indeterminate" in rc_candidate.title.lower() or "insufficient" in rc_candidate.title.lower():
            recommendations.extend(self._generate_insufficient_evidence_actions(rc_candidate, evidence_items))
        else:
            primary_actions = self._generate_actions_for_hypothesis(rc_candidate, evidence_items)
            recommendations.extend(primary_actions)

            # If there are competing alternative hypotheses with close confidence, include disambiguation actions
            if alt_candidates:
                competing_actions = self._generate_competing_hypothesis_actions(
                    primary_rc=rc_candidate,
                    alternatives=alt_candidates,
                    evidence=evidence_items,
                )
                recommendations.extend(competing_actions)

        # 3. Deduplicate and prioritize actions
        prioritized = self._prioritize_and_deduplicate(recommendations)

        # 4. Determine overall human approval requirements
        needs_human_approval = any(a.requires_human_approval for a in prioritized)

        # 5. Formulate findings and executive summary
        findings: List[Finding] = [
            Finding(
                category="RECOMMENDATION",
                title=f"Generated {len(prioritized)} Remediation Action(s)",
                description=(
                    f"Formulated evidence-based remediation plan for root cause: "
                    f"'{rc_candidate.title if rc_candidate else 'Indeterminate'}'. "
                    f"Human approval required: {needs_human_approval}."
                ),
                severity=Severity.INFO,
                affected_devices=rc_candidate.affected_devices if rc_candidate else [],
                metrics={"action_count": len(prioritized), "requires_approval": needs_human_approval},
            )
        ]

        summary = self._formulate_summary(rc_candidate, prioritized, needs_human_approval)

        return RecommendationAgentResponse(
            agent_id=self.agent_id,
            task_id=task_id,
            status=AgentStatus.SUCCESS,
            timestamp=datetime.now(timezone.utc),
            analyzed_hypothesis_count=1 + len(alt_candidates),
            recommendations=prioritized,
            prioritized_actions=prioritized,
            overall_summary=summary,
            confidence=correlation_conf,
            errors=errors,
            requires_human_approval=needs_human_approval,
            findings=findings,
            metadata={
                "actions": [a.model_dump() for a in prioritized],
                "action_count": len(prioritized),
                "requires_human_approval": needs_human_approval,
                "overall_summary": summary,
            },
        )

    # -------------------------------------------------------------------------
    # DOMAIN RECOMMENDATION GENERATORS (SCENARIOS A - G)
    # -------------------------------------------------------------------------

    def _generate_actions_for_hypothesis(
        self,
        rc: RootCauseCandidate,
        evidence: List[EvidenceItem],
    ) -> List[RecommendationItem]:
        title = rc.title.lower()
        devices = rc.affected_devices if rc.affected_devices else ["affected-node"]
        target_dev = devices[0]
        hyp_id = getattr(rc, "hypothesis_id", rc.root_cause_id)
        evidence_texts = [e.details or f"{e.metric_name}: {e.observed_value}" for e in evidence]

        actions: List[RecommendationItem] = []

        # Nominal operation
        if "nominal" in title:
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title="Maintain Baseline Monitoring",
                    category="VERIFICATION",
                    description="System is operating within designated SLA parameters. Continue standard NOC monitoring and periodic SLA validation.",
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P3_MEDIUM.value,
                    severity="info",
                    confidence=rc.confidence,
                    action_type=ActionType.DIAGNOSTIC.value,
                    execution_risk=ExecutionRisk.LOW.value,
                    estimated_impact="Maintains continuous baseline assurance.",
                    prerequisites=[],
                    verification_steps=["Monitor health dashboard gauges for stability."],
                    rollback_steps=[],
                    requires_human_approval=False,
                    automation_command="ping -c 4 8.8.8.8",
                )
            )
            return actions

        # =====================================================================
        # SCENARIO A: Network Congestion & Bufferbloat
        # =====================================================================
        if "congestion" in title or "bufferbloat" in title or "bandwidth" in title:
            # 1. Read-only diagnostic: Top talkers
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title=f"Identify Top-Talker Flows on {target_dev}",
                    category="DIAGNOSTIC",
                    description=(
                        f"Analyze NetFlow/sFlow/IPFIX telemetry on {target_dev} to isolate bandwidth-consuming "
                        "hosts, destination ports, and bulk transfer protocols responsible for link saturation."
                    ),
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P1_CRITICAL.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.DIAGNOSTIC.value,
                    execution_risk=ExecutionRisk.LOW.value,
                    estimated_impact="Pins down specific traffic flows causing link saturation without altering traffic path.",
                    prerequisites=[],
                    verification_steps=["Inspect flow export tables or query flow collector for top 10 IP talkers."],
                    rollback_steps=[],
                    requires_human_approval=False,
                    automation_command=f"ssh admin@{target_dev} 'show flow monitor WAN-MONITOR cache top 10 bytes'",
                )
            )
            # 2. Corrective mitigation: QoS Shaping & Police Bulk Transfers
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title="Apply Traffic Shaping & Prioritize Expedited Forwarding (QoS)",
                    category="IMMEDIATE_MITIGATION",
                    description=(
                        f"Implement Random Early Detection (WRED) or FQ-CoDel on {target_dev} egress queues. "
                        "Rate-limit bulk file transfers and prioritize interactive VoIP/management traffic."
                    ),
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P2_HIGH.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.MITIGATION.value,
                    execution_risk=ExecutionRisk.MEDIUM.value,
                    estimated_impact="Eliminates bufferbloat and reduces packet queuing latency below 40ms.",
                    prerequisites=["Verify QoS policy-map syntax and backup running configuration."],
                    verification_steps=["Verify queue tail drops drop to zero and 95th percentile latency drops below 40ms."],
                    rollback_steps=[f"ssh admin@{target_dev} 'conf t; interface Gi0/1; no service-policy output WAN-EDGE; exit'"],
                    requires_human_approval=True,
                    automation_command=f"ssh admin@{target_dev} 'conf t; policy-map WAN-EDGE; class BULK-TRAFFIC; police 20000000; exit'",
                )
            )
            # 3. Capacity expansion (only when evidence supports sustained congestion)
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title="Enable LACP Link Aggregation / Upgrade Bandwidth Capacity",
                    category="CONFIGURATION",
                    description=(
                        f"Bond redundant physical links into an 802.3ad LACP port-channel on {target_dev} "
                        "or initiate circuit bandwidth upgrade with transit provider."
                    ),
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P3_MEDIUM.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.CAPACITY_EXPANSION.value,
                    execution_risk=ExecutionRisk.MEDIUM.value,
                    estimated_impact="Doubles aggregate throughput capacity and eliminates link bottleneck.",
                    prerequisites=["Verify partner switchport supports LACP and optics are provisioned."],
                    verification_steps=["Run 'show etherchannel summary' and confirm bandwidth utilization drops below 60%."],
                    rollback_steps=["Revert port-channel members to standalone interfaces."],
                    requires_human_approval=True,
                    automation_command=f"ssh admin@{target_dev} 'show etherchannel summary'",
                )
            )

        # =====================================================================
        # SCENARIO B: Infrastructure Overload (CPU / RAM)
        # =====================================================================
        elif "overload" in title or "hardware" in title or "cpu" in title or "memory" in title:
            # 1. Read-only diagnostic: Top CPU processes
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title=f"Identify Top CPU Processes on {target_dev}",
                    category="DIAGNOSTIC",
                    description=(
                        f"Inspect CPU and memory resource consumption on {target_dev}. "
                        "Isolate runaway route recalculations, SNMP polling storms, or daemon memory leaks."
                    ),
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P1_CRITICAL.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.DIAGNOSTIC.value,
                    execution_risk=ExecutionRisk.LOW.value,
                    estimated_impact="Identifies root process pegging supervisor CPU without service interruption.",
                    prerequisites=[],
                    verification_steps=["Verify sorted CPU process output identifies offending daemon."],
                    rollback_steps=[],
                    requires_human_approval=False,
                    automation_command=f"ssh admin@{target_dev} 'show processes cpu sorted | head 10'",
                )
            )
            # 2. Corrective configuration: Control Plane Policing (CoPP)
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title="Configure Control Plane Policing (CoPP)",
                    category="CONFIGURATION",
                    description=(
                        f"Deploy CoPP filter policies on {target_dev} to rate-limit unauthenticated ICMP, "
                        "ARP, or BGP storm packets destined to supervisor engine."
                    ),
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P2_HIGH.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.CONFIGURATION.value,
                    execution_risk=ExecutionRisk.MEDIUM.value,
                    estimated_impact="Shields supervisor engine and drops control plane CPU utilization below 50%.",
                    prerequisites=["Verify routing protocol ACL permits exist in CoPP policy."],
                    verification_steps=["Run 'show policy-map control-plane' and ensure transit CPU drops below 50%."],
                    rollback_steps=[f"ssh admin@{target_dev} 'conf t; control-plane; no service-policy input COPP-POLICY; exit'"],
                    requires_human_approval=True,
                    automation_command=f"ssh admin@{target_dev} 'show policy-map control-plane'",
                )
            )
            # 3. Corrective remediation: Restart stuck service or schedule reboot
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title=f"Restart Stuck Control Plane Daemon on {target_dev}",
                    category="IMMEDIATE_MITIGATION",
                    description=(
                        f"Restart the leaking or stalled process daemon on {target_dev} during maintenance window "
                        "to release exhausted heap memory."
                    ),
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P2_HIGH.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.MITIGATION.value,
                    execution_risk=ExecutionRisk.HIGH.value,
                    estimated_impact="Recovers consumed RAM and prevents catastrophic kernel OOM panic.",
                    prerequisites=["Verify secondary high-availability supervisor node is in hot-standby."],
                    verification_steps=["Verify memory usage drops below 60% and process restarts cleanly."],
                    rollback_steps=["Failover to redundant supervisor engine if process fails to restart."],
                    requires_human_approval=True,
                    automation_command=f"ssh admin@{target_dev} 'restart service routing-engine'",
                )
            )

        # =====================================================================
        # SCENARIO C: DNS Degradation
        # =====================================================================
        elif "dns" in title:
            # 1. Read-only diagnostic: Query upstream resolver
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title="Verify Upstream DNS Resolver Health & Port 53 Reachability",
                    category="DIAGNOSTIC",
                    description=(
                        "Probe primary and secondary DNS forwarders using direct UDP/TCP port 53 queries. "
                        "Check for packet loss, upstream firewall blocking, or resolver timeouts."
                    ),
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P1_CRITICAL.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.DIAGNOSTIC.value,
                    execution_risk=ExecutionRisk.LOW.value,
                    estimated_impact="Identifies whether failure is local resolver misconfiguration or upstream ISP forwarder outage.",
                    prerequisites=[],
                    verification_steps=["Run nslookup / dig directly against resolver IP."],
                    rollback_steps=[],
                    requires_human_approval=False,
                    automation_command="powershell -Command \"Resolve-DnsName -Name google.com -Server 8.8.8.8 -QuickTimeout\"",
                )
            )
            # 2. Corrective: Flush cache (Safe diagnostic mitigation)
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title="Flush Local DNS Resolver Cache",
                    category="IMMEDIATE_MITIGATION",
                    description="Flush local and intermediary resolver caches to eliminate poisoned or stale negative cache entries.",
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P1_CRITICAL.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.MITIGATION.value,
                    execution_risk=ExecutionRisk.LOW.value,
                    estimated_impact="Instantly clears transient resolution errors without service disruption.",
                    prerequisites=[],
                    verification_steps=["Confirm local DNS queries resolve without timeout."],
                    rollback_steps=[],
                    requires_human_approval=False,
                    automation_command="powershell -Command \"Clear-DnsClientCache\"",
                )
            )
            # 3. Corrective: Restart DNS service (Service restart requires human approval)
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title="Restart Local DNS Resolver Service",
                    category="IMMEDIATE_MITIGATION",
                    description="Restart client-side DNS caching resolver daemon to reset socket binding and internal cache states.",
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P2_HIGH.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.MITIGATION.value,
                    execution_risk=ExecutionRisk.MEDIUM.value,
                    estimated_impact="Recovers stalled resolver sockets and restarts name lookup daemon.",
                    prerequisites=["Verify administrative privileges to manage system services."],
                    verification_steps=["Verify service state reports 'Running' after restart."],
                    rollback_steps=["Execute 'Start-Service -Name Dnscache' if service fails to recover."],
                    requires_human_approval=True,
                    automation_command="powershell -Command \"Restart-Service -Name Dnscache\"",
                )
            )
            # 3. Remediation: Failover to Anycast DNS
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title="Failover to Secondary Anycast DNS Resolvers",
                    category="CONFIGURATION",
                    description=(
                        "Update DHCP scope DNS options or client interface settings to use reliable "
                        "secondary Anycast resolvers (e.g., 1.1.1.1, 8.8.8.8)."
                    ),
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P2_HIGH.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.CONFIGURATION.value,
                    execution_risk=ExecutionRisk.MEDIUM.value,
                    estimated_impact="Restores domain name resolution for all clients across the subnet.",
                    prerequisites=["Verify egress port 53 traffic permitted through perimeter firewall."],
                    verification_steps=["Run dig/nslookup and verify query response time is under 30ms with 0% failure rate."],
                    rollback_steps=["Revert DNS server IP addresses to original internal DNS server."],
                    requires_human_approval=True,
                    automation_command="powershell -Command \"Set-DnsClientServerAddress -InterfaceAlias 'Ethernet' -ServerAddresses ('1.1.1.1','8.8.8.8')\"",
                )
            )

        # =====================================================================
        # SCENARIO D: Wireless RF Degradation (Weak Wi-Fi)
        # =====================================================================
        elif "wi-fi" in title or "wireless" in title:
            # 1. Read-only diagnostic: Signal survey & client distance
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title=f"Inspect Wireless RF Signal & Roaming State on {target_dev}",
                    category="DIAGNOSTIC",
                    description=(
                        f"Query wireless NIC statistics on {target_dev}. "
                        "Evaluate RSSI, SNR, current BSSID channel, and physical distance from nearest AP."
                    ),
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P1_CRITICAL.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.DIAGNOSTIC.value,
                    execution_risk=ExecutionRisk.LOW.value,
                    estimated_impact="Pinpoints client coverage hole location without RF disruption.",
                    prerequisites=[],
                    verification_steps=["Confirm current RSSI and connected BSSID."],
                    rollback_steps=[],
                    requires_human_approval=False,
                    automation_command="netsh wlan show interfaces",
                )
            )
            # 2. Corrective: Steer client to closer AP / Adjust AP Transmit Power
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title="Steer Client to 5GHz AP / Increase AP Radio Transmit Power",
                    category="IMMEDIATE_MITIGATION",
                    description=(
                        f"Initiate 802.11k/v BSS transition management to steer client on {target_dev} "
                        "to a closer AP, or adjust AP radio power profile to cover RF dead-zone."
                    ),
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P2_HIGH.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.MITIGATION.value,
                    execution_risk=ExecutionRisk.MEDIUM.value,
                    estimated_impact="Improves RSSI to above -65 dBm and stops packet drops.",
                    prerequisites=["Verify neighboring AP has capacity and acceptable SNR."],
                    verification_steps=["Confirm client reconnects with RSSI > -65 dBm and SNR > 20 dB."],
                    rollback_steps=["Revert radio transmit power to previous dBm level."],
                    requires_human_approval=True,
                    automation_command="netsh wlan show networks mode=bssid",
                )
            )
            # 3. Configuration: Optimize Channel Width
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title="Optimize Channel Width & Dynamic Frequency Selection (DFS)",
                    category="CONFIGURATION",
                    description="Switch congested 80MHz channel to clean 40MHz channel on non-overlapping UNII-2/UNII-3 bands to eliminate co-channel interference.",
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P3_MEDIUM.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.CONFIGURATION.value,
                    execution_risk=ExecutionRisk.MEDIUM.value,
                    estimated_impact="Reduces channel utilization below 25% and eliminates wireless collisions.",
                    prerequisites=["Verify client NIC supports selected 5GHz channels."],
                    verification_steps=["Run wireless survey tool to confirm zero co-channel interference."],
                    rollback_steps=["Revert AP channel configuration to previous channel."],
                    requires_human_approval=True,
                    automation_command="netsh wlan show networks mode=bssid",
                )
            )

        # =====================================================================
        # SCENARIO E: Physical Interface / Cable Failure
        # =====================================================================
        elif "interface" in title or "cable" in title or "crc" in title:
            # 1. Read-only diagnostic: Optical DDM & TDR cable test
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title=f"Perform SFP Optical DDM Diagnostics / TDR Cable Test on {target_dev}",
                    category="DIAGNOSTIC",
                    description=(
                        f"Execute Time-Domain Reflectometry (TDR) on {target_dev} to detect copper distance faults, "
                        "or run DDM to check transceiver Rx/Tx optical power levels."
                    ),
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P1_CRITICAL.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.DIAGNOSTIC.value,
                    execution_risk=ExecutionRisk.LOW.value,
                    estimated_impact="Pinpoints exact physical fault (open/short pair or optical degradation) without taking port down.",
                    prerequisites=[],
                    verification_steps=["Ensure optical Rx power is within range (-12 dBm to -3 dBm) and TDR reports 'Normal'."],
                    rollback_steps=[],
                    requires_human_approval=False,
                    automation_command=f"ssh admin@{target_dev} 'test cable-diagnostics tdr interface Gi0/1'",
                )
            )
            # 2. Corrective: Bounce interface
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title=f"Bounce Interface on {target_dev}",
                    category="IMMEDIATE_MITIGATION",
                    description=(
                        f"Admin-down and admin-up the flapping interface on {target_dev}. "
                        "Clears err-disabled state and reinitializes physical transceiver link training."
                    ),
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P2_HIGH.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.MITIGATION.value,
                    execution_risk=ExecutionRisk.MEDIUM.value,
                    estimated_impact="Restores operational link state if disruption was caused by transient port-security or negotiation glitch.",
                    prerequisites=["Verify redundant STP/LACP uplink path exists before toggling interface."],
                    verification_steps=["Check switchport status displays 'connected' and CRC errors cease incrementing."],
                    rollback_steps=[f"ssh admin@{target_dev} 'conf t; interface GigabitEthernet0/1; no shutdown; exit'"],
                    requires_human_approval=True,
                    automation_command=f"ssh admin@{target_dev} 'conf t; interface GigabitEthernet0/1; shutdown; no shutdown; exit'",
                )
            )
            # 3. Hardware repair: Replace cable / SFP
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title=f"Replace Physical Patch Cable / SFP Transceiver on {target_dev}",
                    category="HARDWARE",
                    description=(
                        f"Physically replace degraded Cat6/Fiber patch cable and reseat/replace the SFP optical module "
                        f"on {target_dev} to eliminate CRC framing corruption."
                    ),
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P3_MEDIUM.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.HARDWARE_REPAIR.value,
                    execution_risk=ExecutionRisk.MEDIUM.value,
                    estimated_impact="Permanently eliminates physical layer CRC errors and link flapping.",
                    prerequisites=["Acquire certified replacement patch cable and compatible vendor-coded SFP."],
                    verification_steps=["Verify port status is 'connected' and CRC counter remains at zero."],
                    rollback_steps=["Re-insert original transceiver if replacement fails to establish link."],
                    requires_human_approval=True,
                    automation_command=f"ssh admin@{target_dev} 'show interfaces GigabitEthernet0/1'",
                )
            )

        # =====================================================================
        # SCENARIO F: DHCP Failure
        # =====================================================================
        elif "dhcp" in title:
            # 1. Read-only diagnostic: Release & renew client IP
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title="Release and Renew Local Client IP Configuration",
                    category="DIAGNOSTIC",
                    description="Trigger DHCP DISCOVER broadcast from affected endpoint to inspect server response and lease binding.",
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P1_CRITICAL.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.DIAGNOSTIC.value,
                    execution_risk=ExecutionRisk.LOW.value,
                    estimated_impact="Tests lease acquisition path without altering server infrastructure.",
                    prerequisites=[],
                    verification_steps=["Verify endpoint acquires valid IPv4 address in scope (not 169.254.x.x)."],
                    rollback_steps=[],
                    requires_human_approval=False,
                    automation_command="powershell -Command \"ipconfig /release; ipconfig /renew\"",
                )
            )
            # 2. Corrective: Expand scope and reclaim expired leases
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title="Expand DHCP Scope & Release Stale Leases",
                    category="IMMEDIATE_MITIGATION",
                    description=(
                        "Inspect DHCP server address scope. Expand subnet mask (e.g., /24 to /23) "
                        "or reduce lease duration (e.g., 8 days to 4 hours) to reclaim inactive IP addresses."
                    ),
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P2_HIGH.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.MITIGATION.value,
                    execution_risk=ExecutionRisk.HIGH.value,
                    estimated_impact="Eliminates IP exhaustion and allows new clients to acquire dynamic network configuration.",
                    prerequisites=["Verify no overlapping static IP allocations in expanded subnet range."],
                    verification_steps=["Confirm DHCP scope utilization drops below 80% and DHCPOFFER packets are delivered."],
                    rollback_steps=["Revert scope IP pool range to previous start/end addresses."],
                    requires_human_approval=True,
                    automation_command="powershell -Command \"Get-DhcpServerv4Scope | Get-DhcpServerv4Lease -ScopeId 192.168.1.0\"",
                )
            )
            # 3. Diagnostic: Verify DHCP relay helper
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title=f"Verify DHCP Relay Helper Configuration on {target_dev}",
                    category="CONFIGURATION",
                    description=f"Inspect 'ip helper-address' configuration on {target_dev} default gateway SVI to ensure broadcasts are forwarded to DHCP server.",
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P2_HIGH.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.CONFIGURATION.value,
                    execution_risk=ExecutionRisk.LOW.value,
                    estimated_impact="Ensures cross-VLAN DHCP discovery packets reach centralized DHCP server.",
                    prerequisites=[],
                    verification_steps=["Verify router interface displays correct helper address and forwarder counter increments."],
                    rollback_steps=[],
                    requires_human_approval=False,
                    automation_command=f"ssh admin@{target_dev} 'show running-config interface Vlan10 | include helper'",
                )
            )

        # =====================================================================
        # SCENARIO H: Rolling Baseline Anomaly / Silent Degradation
        # =====================================================================
        elif "baseline" in title or "drift" in title or "degradation" in title:
            actions.append(
                RecommendationItem(
                    hypothesis_id=hyp_id,
                    title="Investigate Rolling Baseline Metric Drift & Background Workload",
                    category="DIAGNOSTIC",
                    description=(
                        f"Statistical baseline anomaly detected on {target_dev}. Telemetry metric is drifting "
                        "gradually without crossing static SLA thresholds. Inspect background process workload, "
                        "recent routing updates, and link utilization trends."
                    ),
                    affected_devices=devices,
                    supporting_evidence=evidence_texts,
                    priority=ActionPriority.P2_HIGH.value,
                    severity=rc.severity,
                    confidence=rc.confidence,
                    action_type=ActionType.DIAGNOSTIC.value,
                    execution_risk=ExecutionRisk.LOW.value,
                    estimated_impact="Isolates silent degradation root cause before reaching critical SLA thresholds.",
                    prerequisites=[],
                    verification_steps=["Verify if metric returns to baseline distribution after workload isolation."],
                    rollback_steps=[],
                    requires_human_approval=False,
                    automation_command=f"ssh admin@{target_dev} 'show system statistics'",
                )
            )

        # =====================================================================
        # SCENARIO G / FALLBACK: General / Deep Packet Inspection
        # =====================================================================
        else:
            actions.extend(self._generate_insufficient_evidence_actions(rc, evidence))

        return actions

    def _generate_insufficient_evidence_actions(
        self,
        rc: Optional[RootCauseCandidate],
        evidence: List[EvidenceItem],
    ) -> List[RecommendationItem]:
        """
        Generates safe, non-disruptive diagnostic recommendations when evidence is insufficient or ambiguous.
        Prevents disruptive remediation when confidence is low.
        """
        devices = rc.affected_devices if rc and rc.affected_devices else ["affected-node"]
        hyp_id = getattr(rc, "hypothesis_id", "HYP-INDET") if rc else "HYP-INDET"
        evidence_texts = [e.details or f"{e.metric_name}: {e.observed_value}" for e in evidence]

        return [
            RecommendationItem(
                hypothesis_id=hyp_id,
                title="Enable Targeted Packet Capture & Diagnostic Trace",
                category="DIAGNOSTIC",
                description=(
                    "Available telemetry evidence is ambiguous or lacks cross-agent corroboration. "
                    "Deploy non-intrusive packet capture (Wireshark/tcpdump) on affected interface and collect synchronized syslog."
                ),
                affected_devices=devices,
                supporting_evidence=evidence_texts,
                priority=ActionPriority.P1_CRITICAL.value,
                severity="warning",
                confidence=rc.confidence if rc else 0.30,
                action_type=ActionType.DIAGNOSTIC.value,
                execution_risk=ExecutionRisk.LOW.value,
                estimated_impact="Gathers conclusive packet-level evidence to isolate root cause without network disruption.",
                prerequisites=["Ensure monitoring host has sufficient disk space for ring buffer pcap."],
                verification_steps=["Verify capture file is non-empty and contains bidirectional protocol handshakes."],
                rollback_steps=["Stop tcpdump process and remove capture file."],
                requires_human_approval=False,
                automation_command="tcpdump -i any -c 2000 -w /tmp/diag_capture.pcap",
            ),
            RecommendationItem(
                hypothesis_id=hyp_id,
                title="Increase Telemetry Polling Frequency",
                category="DIAGNOSTIC",
                description=(
                    "Increase SNMP/telemetry sampling frequency from 60 seconds to 5 seconds across affected nodes "
                    "to capture transient microbursts and intermittent anomalies."
                ),
                affected_devices=devices,
                supporting_evidence=evidence_texts,
                priority=ActionPriority.P2_HIGH.value,
                severity="warning",
                confidence=rc.confidence if rc else 0.30,
                action_type=ActionType.DIAGNOSTIC.value,
                execution_risk=ExecutionRisk.LOW.value,
                estimated_impact="Provides high-resolution time-series data to disambiguate competing root causes.",
                prerequisites=[],
                verification_steps=["Confirm ingest pipeline receives 5-second interval metric streams."],
                rollback_steps=["Revert polling interval to standard 60 seconds."],
                requires_human_approval=False,
                automation_command="powershell -Command \"Set-Service -Name snmp -StartupType Automatic\"",
            ),
        ]

    def _generate_competing_hypothesis_actions(
        self,
        primary_rc: RootCauseCandidate,
        alternatives: List[RootCauseCandidate],
        evidence: List[EvidenceItem],
    ) -> List[RecommendationItem]:
        """
        Generates diagnostic disambiguation recommendations when multiple competing hypotheses are plausible.
        """
        alt_titles = [alt.title for alt in alternatives[:2]]
        hyp_id = getattr(primary_rc, "hypothesis_id", primary_rc.root_cause_id)
        devices = primary_rc.affected_devices

        return [
            RecommendationItem(
                hypothesis_id=hyp_id,
                title=f"Disambiguate Competing Hypotheses: {primary_rc.title} vs {alt_titles[0]}",
                category="DIAGNOSTIC",
                description=(
                    f"Telemetry signals exhibit symptoms compatible with both '{primary_rc.title}' and '{alt_titles[0]}'. "
                    "Perform targeted comparative checks before applying disruptive configuration changes."
                ),
                affected_devices=devices,
                supporting_evidence=[f"Competing explanations: {primary_rc.title} ({primary_rc.confidence:.2f}) vs {alt_titles[0]}"],
                priority=ActionPriority.P1_CRITICAL.value,
                severity="warning",
                confidence=primary_rc.confidence,
                action_type=ActionType.DIAGNOSTIC.value,
                execution_risk=ExecutionRisk.LOW.value,
                estimated_impact="Prevents misdirected remediation by conclusively confirming true fault driver.",
                prerequisites=[],
                verification_steps=["Verify if metric anomaly correlates with interface traffic vs device control plane."],
                rollback_steps=[],
                requires_human_approval=False,
                automation_command="netsh trace start capture=yes tracefile=C:\\temp\\nettrace.etl maxsize=250",
            )
        ]

    # -------------------------------------------------------------------------
    # PRIORITIZATION & DEDUPLICATION
    # -------------------------------------------------------------------------

    def _prioritize_and_deduplicate(
        self,
        recommendations: List[RecommendationItem],
    ) -> List[RecommendationItem]:
        seen_titles: Set[str] = set()
        deduped: List[RecommendationItem] = []

        for item in recommendations:
            normalized_title = item.title.strip().lower()
            if normalized_title in seen_titles:
                continue
            seen_titles.add(normalized_title)
            deduped.append(item)

        # Sorting rule:
        # 1. Diagnostic actions (ExecutionRisk.LOW) with Priority 1 first
        # 2. Priority order (1 to 5)
        # 3. Execution risk (LOW before MEDIUM before HIGH)
        risk_weights = {ExecutionRisk.LOW.value: 1, ExecutionRisk.MEDIUM.value: 2, ExecutionRisk.HIGH.value: 3}

        def sort_key(action: RecommendationItem) -> Tuple[int, int, float]:
            prio = action.priority
            risk = risk_weights.get(action.execution_risk, 2)
            # High-impact diagnostic actions should precede disruptive ones
            return (prio, risk, -action.confidence)

        deduped.sort(key=sort_key)
        return deduped

    # -------------------------------------------------------------------------
    # INPUT NORMALIZATION & EXTRACTION
    # -------------------------------------------------------------------------

    def _extract_correlation_data(
        self,
        correlation_input: Any,
        errors: List[str],
    ) -> Tuple[Optional[RootCauseCandidate], List[RootCauseCandidate], List[EvidenceItem], float]:
        rc_candidate: Optional[RootCauseCandidate] = None
        alt_candidates: List[RootCauseCandidate] = []
        evidence_items: List[EvidenceItem] = []
        confidence = 0.50

        if correlation_input is None:
            errors.append("Null correlation input provided.")
            return None, [], [], 0.0

        if isinstance(correlation_input, RootCauseCandidate):
            return correlation_input, [], [], correlation_input.confidence

        meta: Dict[str, Any] = {}

        if hasattr(correlation_input, "metadata") and isinstance(correlation_input.metadata, dict):
            meta = correlation_input.metadata
            confidence = getattr(correlation_input, "confidence", 0.50)
            evidence_items = getattr(correlation_input, "evidence", [])
        elif hasattr(correlation_input, "primary_hypothesis"):
            # Direct CorrelationResponse object
            hyp = correlation_input.primary_hypothesis
            if hyp:
                rc_candidate = RootCauseCandidate.model_validate(hyp.model_dump())
            alt_candidates = [RootCauseCandidate.model_validate(a.model_dump()) for a in getattr(correlation_input, "alternative_hypotheses", [])]
            evidence_items = getattr(correlation_input, "evidence", [])
            confidence = getattr(correlation_input, "confidence", 0.50)
            return rc_candidate, alt_candidates, evidence_items, confidence
        elif isinstance(correlation_input, dict):
            meta = correlation_input.get("metadata", correlation_input)
            confidence = correlation_input.get("confidence", 0.50)
            evidence_items = correlation_input.get("evidence", [])

        # Extract probable_root_cause from metadata
        if "probable_root_cause" in meta and meta["probable_root_cause"]:
            raw_rc = meta["probable_root_cause"]
            try:
                if isinstance(raw_rc, dict):
                    rc_candidate = RootCauseCandidate.model_validate(raw_rc)
                elif hasattr(raw_rc, "model_dump"):
                    rc_candidate = RootCauseCandidate.model_validate(raw_rc.model_dump())
            except Exception as exc:
                errors.append(f"Failed to parse probable_root_cause: {exc}")

        # Extract alternative causes
        if "alternative_causes" in meta and isinstance(meta["alternative_causes"], list):
            for raw_alt in meta["alternative_causes"]:
                try:
                    if isinstance(raw_alt, dict):
                        alt_candidates.append(RootCauseCandidate.model_validate(raw_alt))
                    elif hasattr(raw_alt, "model_dump"):
                        alt_candidates.append(RootCauseCandidate.model_validate(raw_alt.model_dump()))
                except Exception:
                    pass

        return rc_candidate, alt_candidates, evidence_items, confidence

    def _formulate_summary(
        self,
        rc: Optional[RootCauseCandidate],
        actions: List[RecommendationItem],
        needs_approval: bool,
    ) -> str:
        count = len(actions)
        diag_count = len([a for a in actions if a.action_type == ActionType.DIAGNOSTIC.value or a.execution_risk == ExecutionRisk.LOW.value])
        disrupt_count = count - diag_count
        approval_str = "Human approval required for disruptive remediation." if needs_approval else "All recommendations are low-risk diagnostics."

        rc_title = rc.title if rc else "Indeterminate"
        return (
            f"Remediation plan for '{rc_title}': Generated {count} prioritized action(s) "
            f"({diag_count} safe diagnostic(s), {disrupt_count} configuration change(s)). {approval_str}"
        )
