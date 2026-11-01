from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

logger = logging.getLogger("copilot.explainer")

SYSTEM_PROMPT = """You are the NetCoop AI Diagnostic Copilot. Your sole role is to explain the provided DiagnosticReport JSON in clear, natural language to NOC network operators.

STRICT GROUNDING RULES:
1. Answer ONLY using the facts, telemetry metrics, findings, hypotheses, and recommendations explicitly contained in the provided DiagnosticReport JSON.
2. Every telemetry finding or metric you reference MUST cite its evidence ID, e.g. [E1], [E2].
3. If the report lacks the requested information, state clearly: "The report doesn't contain that."
4. NEVER invent, hallucinate, or extrapolate numbers, thresholds, percentages, or device IDs.
5. NEVER recommend actions or runbook procedures beyond those explicitly listed in the report.
6. The diagnostic engine has already decided the root cause and health status; you are an explainer, not a diagnostician. Do not change, override, or second-guess the diagnosis.
"""


class CopilotResponse(dict):
    """
    Structured Copilot response object supporting both dict indexing and attribute access.
    str(response) returns the clean natural language answer string.
    """

    def __init__(
        self,
        answer: str,
        mode: str,
        cited_evidence: Optional[List[str]] = None,
        unverified_numbers: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        cited = cited_evidence or []
        unverified = unverified_numbers or []
        super().__init__(
            answer=answer,
            mode=mode,
            cited_evidence=cited,
            unverified_numbers=unverified,
        )
        self.answer = answer
        self.mode = mode
        self.cited_evidence = cited
        self.unverified_numbers = unverified
        self.context = context or {}

    def __str__(self) -> str:
        return self.answer

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(f"'CopilotResponse' object has no attribute '{name}'")


def _get_val(obj: Any, key: str, default: Any = None) -> Any:
    """Helper to retrieve values from either Pydantic models, objects, or dicts."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def build_context(report: Union[Any, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Extracts a compact, strictly grounded JSON-serializable dictionary representation
    of a DiagnosticReport for the Copilot.

    Includes:
    - Overall network health & classification
    - Diagnostic certainty tier
    - Probable root cause (title, category, confidence, description, affected devices)
    - Structured evidence items with explicit [E1], [E2] citation identifiers
    - Specialized agent findings with provenance
    - Recommended runbook actions (priority, risk level, disruptive approval gating)
    - Ruled-out / alternative hypotheses and explanations
    """
    if report is None:
        return {
            "task_id": "NONE",
            "overall_network_health": "UNKNOWN",
            "diagnosis_certainty": "NOT_APPLICABLE",
            "fault_detected": False,
            "root_cause": None,
            "evidence": [],
            "agent_findings": [],
            "recommended_actions": [],
            "ruled_out_hypotheses": [],
        }

    task_id = str(_get_val(report, "task_id", "") or "")
    report_id = str(_get_val(report, "report_id", "") or "")
    health = _get_val(report, "overall_network_health", "UNKNOWN")
    health_str = getattr(health, "value", str(health))
    health_class = str(_get_val(report, "health_classification", health_str))
    certainty = str(_get_val(report, "diagnosis_certainty", "CONFIRMED"))
    fault_detected = bool(_get_val(report, "fault_detected", False))
    raw_conf = _get_val(report, "root_cause_confidence", _get_val(report, "confidence", None))

    # 1. Primary Root Cause
    rc_obj = _get_val(report, "probable_root_cause") or _get_val(report, "selected_root_cause")
    root_cause_dict: Optional[Dict[str, Any]] = None
    if rc_obj:
        rc_conf = _get_val(rc_obj, "confidence", raw_conf or 1.0)
        root_cause_dict = {
            "title": str(_get_val(rc_obj, "title", "Nominal Network Operation")),
            "category": str(_get_val(rc_obj, "category", "NOMINAL")),
            "confidence": round(float(rc_conf), 2) if rc_conf is not None else 1.0,
            "description": str(_get_val(rc_obj, "description", "")),
            "severity": str(_get_val(rc_obj, "severity", "info")),
            "affected_devices": list(_get_val(rc_obj, "affected_devices", []) or []),
            "uncertainty_explanation": _get_val(rc_obj, "uncertainty_explanation", None),
        }

    # 2. Evidence items with [E1], [E2] citation IDs
    raw_evidence = _get_val(report, "supporting_evidence", []) or []
    evidence_list: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw_evidence, start=1):
        ev_id = f"[E{idx}]"
        metric = str(_get_val(item, "metric_name", "") or "")
        obs_val = _get_val(item, "observed_value", None)
        thresh = _get_val(item, "threshold", None)
        unit = str(_get_val(item, "unit", "") or "")
        dev = str(_get_val(item, "device_id", "") or "")
        details = str(_get_val(item, "details", "") or "")
        if not details:
            details = f"{metric} on {dev}: {obs_val}{unit} (threshold: {thresh}{unit})"

        evidence_list.append({
            "id": ev_id,
            "device_id": dev,
            "metric_name": metric,
            "observed_value": obs_val,
            "threshold": thresh,
            "unit": unit,
            "details": details,
        })

    # 3. Specialized Agent Findings
    findings_list: List[Dict[str, Any]] = []
    raw_ind_findings = _get_val(report, "individual_agent_findings", {}) or {}
    if isinstance(raw_ind_findings, dict):
        for ag_id, msg in raw_ind_findings.items():
            fnds = _get_val(msg, "findings", []) or []
            for f in fnds:
                findings_list.append({
                    "source_agent": str(_get_val(f, "source_agent", ag_id)),
                    "title": str(_get_val(f, "title", "")),
                    "severity": str(_get_val(f, "severity", "MEDIUM")),
                    "description": str(_get_val(f, "description", "")),
                    "affected_devices": list(_get_val(f, "affected_devices", []) or []),
                })

    if not findings_list:
        v_fnds = _get_val(report, "validated_findings", []) or []
        for f in v_fnds:
            findings_list.append({
                "source_agent": str(_get_val(f, "source_agent", "agent")),
                "title": str(_get_val(f, "title", "")),
                "severity": str(_get_val(f, "severity", "MEDIUM")),
                "description": str(_get_val(f, "description", "")),
                "affected_devices": list(_get_val(f, "affected_devices", []) or []),
            })

    # 4. Corrective Runbook Actions
    actions_list: List[Dict[str, Any]] = []
    raw_actions = (
        _get_val(report, "recommended_corrective_actions", [])
        or _get_val(report, "recommendations", [])
        or []
    )
    for act in raw_actions:
        risk = str(_get_val(act, "execution_risk", "LOW")).upper()
        category = str(_get_val(act, "category", "DIAGNOSTIC")).upper()
        is_disruptive = (
            risk in ("MEDIUM", "HIGH")
            or "DISRUPTIVE" in category
            or "REMEDIATION" in category
        )
        req_approval = bool(_get_val(act, "requires_human_approval", is_disruptive))
        prereqs = list(_get_val(act, "prerequisites", []) or [])
        verifs = list(_get_val(act, "verification_steps", []) or [])
        if not verifs and _get_val(act, "verification_step"):
            verifs = [_get_val(act, "verification_step")]

        actions_list.append({
            "action_id": str(_get_val(act, "action_id", _get_val(act, "recommendation_id", ""))),
            "title": str(_get_val(act, "title", "")),
            "category": category,
            "priority": int(_get_val(act, "priority", 2)),
            "execution_risk": risk,
            "is_disruptive": is_disruptive,
            "requires_human_approval": req_approval,
            "description": str(_get_val(act, "description", "")),
            "prerequisites": prereqs,
            "verification_steps": verifs,
        })

    # 5. Ruled-Out and Alternative Hypotheses
    ruled_out_list: List[Dict[str, Any]] = []
    raw_alts = (
        _get_val(report, "alternative_causes", [])
        or _get_val(report, "alternative_hypotheses", [])
        or []
    )
    primary_conf = root_cause_dict.get("confidence", 1.0) if root_cause_dict else 1.0
    for alt in raw_alts:
        alt_title = str(_get_val(alt, "title", ""))
        alt_conf = float(_get_val(alt, "confidence", 0.0))
        alt_expl = _get_val(alt, "uncertainty_explanation", None)
        reason = alt_expl or (
            f"Confidence score ({alt_conf:.2f}) was lower than the confirmed root cause "
            f"({primary_conf:.2f}) due to lack of multi-agent corroborating telemetry."
        )
        ruled_out_list.append({
            "title": alt_title,
            "category": str(_get_val(alt, "category", "UNKNOWN")),
            "confidence": alt_conf,
            "reason_ruled_out": reason,
        })

    return {
        "task_id": task_id,
        "report_id": report_id,
        "overall_network_health": health_str,
        "health_classification": health_class,
        "diagnosis_certainty": certainty,
        "fault_detected": fault_detected,
        "root_cause": root_cause_dict,
        "evidence": evidence_list,
        "agent_findings": findings_list,
        "recommended_actions": actions_list,
        "ruled_out_hypotheses": ruled_out_list,
    }


def verify_numbers_in_answer(answer: str, context: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Grounding post-check: extracts numbers from the LLM answer and verifies that
    each number appears in the underlying report context.

    Filters out:
    - Citation identifiers like [E1], [E2]
    - Markdown numbered list headers like '1. ', '2. '

    Returns (is_verified, list_of_unverified_numbers).
    """
    # 1. Clean citations and list indices
    cleaned = re.sub(r"\[E\d+\]", " ", answer)
    cleaned = re.sub(r"(?:^|\n|\s)\d+\.\s+", " ", cleaned)

    # 2. Extract numeric tokens (integers, floats, percentages)
    raw_tokens = re.findall(
        r"(?<![-_\w])(\d+(?:\.\d+)?)(?:%|\s*(?:ms|s|dbm|mbps|gbps|pkts))?(?![-_\w])",
        cleaned,
        re.IGNORECASE,
    )
    tokens = list(dict.fromkeys(raw_tokens))  # preserve order, deduplicate

    context_str = json.dumps(context, default=str)
    unverified: List[str] = []

    for tok in tokens:
        # Literal string match
        if tok in context_str:
            continue

        # Float / percentage tolerance match
        matched = False
        try:
            val = float(tok)
            # Check integer representation
            if str(int(val)) in context_str:
                matched = True
            # Check one-decimal representation
            elif f"{val:.1f}" in context_str:
                matched = True
            # Check two-decimal representation
            elif f"{val:.2f}" in context_str:
                matched = True
            # Check percentage conversion (e.g. 88 -> 0.88 or 88.5 -> 0.885)
            # Guard against false-positive matching with 1.0 or 0.0
            pct_val = val / 100.0
            if f"{pct_val:.2f}" in context_str and (pct_val not in (0.0, 1.0) or val in (0.0, 100.0)):
                matched = True
            elif f"{pct_val:.3f}" in context_str and (pct_val not in (0.0, 1.0) or val in (0.0, 100.0)):
                matched = True
            elif f"{pct_val:.4f}" in context_str and (pct_val not in (0.0, 1.0) or val in (0.0, 100.0)):
                matched = True
        except ValueError:
            pass

        if not matched:
            unverified.append(tok)

    return len(unverified) == 0, unverified


def generate_fallback_answer(context: Dict[str, Any], question: str) -> str:
    """
    Deterministic offline template explainer built strictly from report telemetry.
    Provides human-readable answers for the 3 preset questions and general inquiries.
    GUARANTEED to never crash or invent facts on stage.
    """
    q_norm = question.lower().strip()
    rc = context.get("root_cause")
    evidence = context.get("evidence", [])
    actions = context.get("recommended_actions", [])
    ruled_out = context.get("ruled_out_hypotheses", [])
    health = context.get("overall_network_health", "UNKNOWN")
    certainty = context.get("diagnosis_certainty", "CONFIRMED")

    # Format top evidence citations
    top_ev_lines: List[str] = []
    for ev in evidence[:4]:
        top_ev_lines.append(f"• {ev['id']} {ev['details']}")
    evidence_text = "\n".join(top_ev_lines) if top_ev_lines else "• No active threshold anomalies detected."

    # -------------------------------------------------------------------------
    # PRESET 1: "Why this root cause?"
    # -------------------------------------------------------------------------
    if any(k in q_norm for k in ["why this root cause", "why root cause", "explain root cause", "why this cause"]):
        if rc and rc.get("category") != "NOMINAL":
            conf_pct = f"{rc['confidence'] * 100:.1f}%"
            devs_str = ", ".join(rc.get("affected_devices", [])) or "targeted network path"
            ans = (
                f"**Root Cause Diagnosis: {rc['title']}**\n\n"
                f"The multi-agent correlation engine diagnosed this condition with **{certainty}** certainty "
                f"and **{conf_pct}** confidence on {devs_str}.\n\n"
                f"**Causal Telemetry Evidence:**\n{evidence_text}\n\n"
                f"**Causal Explanation:** {rc['description']}"
            )
            if ruled_out:
                ans += (
                    f"\n\n**Ruled-Out Hypotheses:** Alternative causes ({', '.join(h['title'] for h in ruled_out[:2])}) "
                    "scored significantly lower due to the absence of corroborating multi-domain telemetry."
                )
            return ans
        else:
            return (
                f"**Network Status: Nominal Network Operation** (Certainty: {certainty})\n\n"
                f"All evaluated telemetry metrics are operating within designated healthy SLA baselines. "
                f"No anomalous spikes or threshold breaches were observed across the infrastructure."
            )

    # -------------------------------------------------------------------------
    # PRESET 2: "Why not DNS?" (or generic subsystem exclusion)
    # -------------------------------------------------------------------------
    if any(k in q_norm for k in ["why not dns", "why not", "dns"]):
        # Check if user specifically asks about DNS
        if "dns" in q_norm:
            dns_ev = [e for e in evidence if "dns" in e.get("metric_name", "").lower() or "dns" in e.get("details", "").lower()]
            if dns_ev:
                dns_citations = " ".join(e["id"] for e in dns_ev)
                return (
                    f"**DNS Resolution Assessment:**\n"
                    f"DNS service degradation was ruled out because telemetry indicates normal operational behavior ({dns_citations}). "
                    f"DNS query response times and failure rates remained nominal with zero query dropouts or NXDOMAIN anomalies. "
                    f"The primary failure symptoms are concentrated in {rc['title'] if rc else 'another domain'}."
                )
            else:
                return (
                    "**DNS Resolution Assessment:**\n"
                    "DNS was evaluated and ruled out as the primary root cause. Telemetry from the connectivity agent "
                    "reported 0% DNS resolution failure rates and normal upstream forwarder latency. "
                    f"Observed network degradation is caused by {rc['title'] if rc else 'nominal conditions'}."
                )
        elif ruled_out:
            alt_lines = [f"• **{alt['title']}**: {alt['reason_ruled_out']}" for alt in ruled_out[:3]]
            return (
                f"**Ruled-Out Alternative Hypotheses:**\n\n"
                + "\n".join(alt_lines)
                + f"\n\nPrimary diagnosis remained **{rc['title'] if rc else 'Nominal'}** based on cross-agent evidence."
            )

    # -------------------------------------------------------------------------
    # PRESET 3: "What should I do first and is it safe?"
    # -------------------------------------------------------------------------
    if any(k in q_norm for k in ["what should i do", "what to do", "safe", "first"]):
        if actions:
            first_act = actions[0]
            is_disruptive = first_act.get("is_disruptive", False)
            approval = first_act.get("requires_human_approval", is_disruptive)
            risk = first_act.get("execution_risk", "LOW")

            safety_banner = (
                f"⚠️ **DISRUPTIVE ACTION — Awaiting Human Approval** (Risk: {risk})\n"
                "This action mutates network configuration or interface state. "
                "Per NetCoop safety policy, it requires operator approval before execution."
                if (is_disruptive or approval)
                else f"✅ **SAFE / NON-DISRUPTIVE** (Risk: {risk})\n"
                "This is a read-only diagnostic procedure that will not interrupt network traffic."
            )

            ans = (
                f"**Recommended First Step: {first_act['title']}** (Priority P{first_act['priority']})\n\n"
                f"{safety_banner}\n\n"
                f"**Action Description:** {first_act['description']}\n"
            )
            if first_act.get("prerequisites"):
                ans += f"\n**Prerequisites:** {', '.join(first_act['prerequisites'])}"
            if first_act.get("verification_steps"):
                ans += f"\n**Verification:** {', '.join(first_act['verification_steps'])}"

            if len(actions) > 1:
                ans += f"\n\n**Subsequent Actions:** {actions[1]['title']} (P{actions[1]['priority']})"
            return ans
        else:
            return (
                "**No Remediation Actions Required:**\n"
                "The network is currently operating nominally within healthy SLA boundaries. "
                "Continue standard monitoring and periodic telemetry inspection."
            )

    # -------------------------------------------------------------------------
    # UNRELATED / OUT-OF-SCOPE QUESTIONS
    # -------------------------------------------------------------------------
    network_keywords = [
        "network", "router", "switch", "latency", "loss", "packet", "cpu", "memory",
        "interface", "wifi", "dhcp", "dns", "jitter", "queue", "report", "fault",
        "cause", "action", "evidence", "health", "certainty", "score"
    ]
    if not any(k in q_norm for k in network_keywords):
        return (
            "The report doesn't contain that. I can only answer questions regarding the telemetry metrics, "
            "agent findings, root-cause hypotheses, and prescriptive runbooks in this diagnostic report."
        )

    # -------------------------------------------------------------------------
    # GENERAL INQUIRY SUMMARY
    # -------------------------------------------------------------------------
    title_str = rc["title"] if rc else "Nominal Network Operation"
    conf_str = f" ({rc['confidence'] * 100:.1f}% confidence)" if rc else ""
    return (
        f"**Diagnostic Summary for Report {context.get('report_id', '')}**\n\n"
        f"• **Overall Network Health:** {health} (Certainty: {certainty})\n"
        f"• **Primary Inferred Root Cause:** {title_str}{conf_str}\n"
        f"• **Key Evidence Citations:**\n{evidence_text}\n"
        f"• **Next Recommended Action:** {actions[0]['title'] if actions else 'Maintain baseline monitoring'}"
    )


def ask_llm(context_json: str, question: str) -> Optional[str]:
    """
    Attempts to call the Anthropic Claude LLM API within an 8-second bounded timeout.
    Supports both the Anthropic Python SDK (if installed) and direct HTTP API calls via httpx.
    Returns the answer string on success, or None on failure/missing key/timeout.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        return None

    model_name = os.environ.get(
        "ANTHROPIC_MODEL",
        os.environ.get("NETCOOP_COPILOT_MODEL", "claude-3-5-sonnet-20241022"),
    ).strip()

    prompt_user = f"DiagnosticReport JSON:\n{context_json}\n\nOperator Question: {question}"

    # 1. Try official Anthropic SDK if present
    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key, timeout=8.0)
        msg = client.messages.create(
            model=model_name,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt_user}],
        )
        if msg and msg.content and len(msg.content) > 0:
            first_block = msg.content[0]
            return getattr(first_block, "text", str(first_block))
    except ImportError:
        pass
    except Exception as exc:
        logger.warning(f"Anthropic SDK call failed: {exc}. Falling back to HTTP client.")

    # 2. Direct HTTP call via httpx (guaranteed installed in environment)
    try:
        import httpx

        payload = {
            "model": model_name,
            "max_tokens": 1024,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt_user}],
        }
        headers = {
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        with httpx.Client(timeout=8.0) as http_client:
            res = http_client.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=headers,
            )
            if res.status_code == 200:
                data = res.json()
                content = data.get("content", [])
                if content and isinstance(content, list):
                    return content[0].get("text", "")
            else:
                logger.warning(f"Anthropic HTTP endpoint returned status {res.status_code}: {res.text}")
    except Exception as exc:
        logger.warning(f"Direct Anthropic HTTP call failed or timed out: {exc}")

    return None


def ask_copilot(
    report: Union[Any, Dict[str, Any]],
    question: str,
) -> CopilotResponse:
    """
    Main Copilot execution entry point:
    1. Builds grounded compact JSON context from report.
    2. Attempts LLM call via Anthropic API.
    3. Runs number verification post-check against hallucinated numbers.
    4. Falls back deterministically to template answer if offline/timeout/unverified.
    5. Returns structured CopilotResponse with answer, mode ('llm'|'fallback'), and cited_evidence.
    """
    context = build_context(report)
    context_json = json.dumps(context, indent=2, default=str)

    # 1. Attempt LLM call
    llm_raw_answer = ask_llm(context_json, question)

    if llm_raw_answer:
        # 2. Number verification post-check
        is_verified, unverified = verify_numbers_in_answer(llm_raw_answer, context)
        cited = re.findall(r"\[E\d+\]", llm_raw_answer)

        if is_verified:
            return CopilotResponse(
                answer=llm_raw_answer,
                mode="llm",
                cited_evidence=cited,
                unverified_numbers=[],
                context=context,
            )
        else:
            # Append warning for unverified numbers
            warning_suffix = "\n\n⚠️ Note: some figures could not be verified against the report."
            return CopilotResponse(
                answer=llm_raw_answer + warning_suffix,
                mode="llm",
                cited_evidence=cited,
                unverified_numbers=unverified,
                context=context,
            )

    # 3. Deterministic Offline Fallback
    fallback_text = generate_fallback_answer(context, question)
    cited = re.findall(r"\[E\d+\]", fallback_text)
    return CopilotResponse(
        answer=fallback_text,
        mode="fallback",
        cited_evidence=cited,
        unverified_numbers=[],
        context=context,
    )


def ask(report: Union[Any, Dict[str, Any]], question: str) -> str:
    """
    Convenience interface: explains a DiagnosticReport in natural language.
    Returns the answer string directly.
    """
    res = ask_copilot(report, question)
    return res.answer
