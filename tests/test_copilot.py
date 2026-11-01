from __future__ import annotations

import json
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from api.main import app
from copilot.explainer import (
    SYSTEM_PROMPT,
    CopilotResponse,
    ask,
    ask_copilot,
    build_context,
    generate_fallback_answer,
    verify_numbers_in_answer,
)
from data.scenarios import generate_scenario_data
from diagnosis.models import DiagnosticReport, NetworkHealthStatus
from orchestrator.orchestrator import CentralOrchestrator


@pytest.fixture(scope="module")
def sample_congestion_report() -> DiagnosticReport:
    """Creates a sample diagnostic report representing network congestion."""
    orch = CentralOrchestrator()
    records = generate_scenario_data("congestion")
    report = orch.run_diagnosis(records, scenario_name="congestion", save_report=True)
    return report


@pytest.fixture(scope="module")
def sample_normal_report() -> DiagnosticReport:
    """Creates a sample diagnostic report representing nominal network health."""
    orch = CentralOrchestrator()
    records = generate_scenario_data("normal")
    report = orch.run_diagnosis(records, scenario_name="normal", save_report=True)
    return report


def test_build_context_with_none():
    """Context builder should gracefully handle None input."""
    ctx = build_context(None)
    assert ctx["overall_network_health"] == "UNKNOWN"
    assert ctx["fault_detected"] is False
    assert ctx["evidence"] == []
    assert ctx["recommended_actions"] == []


def test_build_context_structure(sample_congestion_report):
    """Context builder should extract all required fields with explicit citation IDs."""
    ctx = build_context(sample_congestion_report)
    assert "task_id" in ctx
    assert "overall_network_health" in ctx
    assert "diagnosis_certainty" in ctx
    assert "root_cause" in ctx
    assert "evidence" in ctx
    assert "agent_findings" in ctx
    assert "recommended_actions" in ctx
    assert "ruled_out_hypotheses" in ctx

    # Check evidence formatting
    assert len(ctx["evidence"]) > 0
    for idx, ev in enumerate(ctx["evidence"], start=1):
        assert ev["id"] == f"[E{idx}]"
        assert "metric_name" in ev
        assert "details" in ev

    # Check root cause
    assert ctx["root_cause"] is not None
    assert ctx["root_cause"]["title"]
    assert ctx["root_cause"]["confidence"] > 0.0

    # Check actions
    if ctx["recommended_actions"]:
        first_act = ctx["recommended_actions"][0]
        assert "title" in first_act
        assert "is_disruptive" in first_act
        assert "requires_human_approval" in first_act


def test_verify_numbers_grounded(sample_congestion_report):
    """Numbers that exist in the context should pass verification."""
    ctx = build_context(sample_congestion_report)
    first_ev = ctx["evidence"][0]
    obs_val = first_ev.get("observed_value")
    conf = ctx["root_cause"]["confidence"]

    ans = f"The latency spiked to {obs_val} according to [E1], with confidence {conf * 100:.1f}%."
    is_verified, unverified = verify_numbers_in_answer(ans, ctx)
    assert is_verified is True
    assert unverified == []


def test_verify_numbers_hallucinated(sample_congestion_report):
    """Invented numbers not in context should be caught by verification check."""
    ctx = build_context(sample_congestion_report)
    ans = "We observed extreme packet loss of 99.87% on interface eth0."
    is_verified, unverified = verify_numbers_in_answer(ans, ctx)
    assert is_verified is False
    assert "99.87" in unverified


def test_fallback_preset_why_root_cause(sample_congestion_report):
    """Offline fallback answers 'Why this root cause?' citing evidence."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
        res = ask_copilot(sample_congestion_report, "Why this root cause?")
        assert isinstance(res, CopilotResponse)
        assert res.mode == "fallback"
        assert sample_congestion_report.probable_root_cause.title in res.answer
        assert "[E1]" in res.answer
        assert len(res.cited_evidence) > 0


def test_fallback_preset_why_not_dns(sample_congestion_report):
    """Offline fallback explains why DNS was excluded/ruled out."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
        res = ask_copilot(sample_congestion_report, "Why not DNS?")
        assert res.mode == "fallback"
        assert "DNS" in res.answer
        assert "ruled out" in res.answer.lower() or "nominal" in res.answer.lower()


def test_fallback_preset_what_first(sample_congestion_report):
    """Offline fallback prioritizes first action and notes safety/approval gating."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
        res = ask_copilot(sample_congestion_report, "What should I do first and is it safe?")
        assert res.mode == "fallback"
        actions = sample_congestion_report.recommended_corrective_actions or sample_congestion_report.recommendations
        first_act = actions[0]
        assert first_act.title in res.answer
        assert ("awaiting human approval" in res.answer.lower()) or ("safe" in res.answer.lower())


def test_fallback_out_of_scope(sample_congestion_report):
    """Questions outside network telemetry return grounded out-of-scope reply."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
        res = ask_copilot(sample_congestion_report, "What is the capital of France?")
        assert res.mode == "fallback"
        assert "The report doesn't contain that" in res.answer


def test_fallback_nominal_network(sample_normal_report):
    """Offline fallback on healthy network clearly states nominal baseline."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
        res = ask_copilot(sample_normal_report, "Why this root cause?")
        assert res.mode == "fallback"
        assert "Nominal Network Operation" in res.answer or "healthy" in res.answer.lower()


def test_mocked_llm_grounded_response(sample_congestion_report):
    """When LLM API succeeds and numbers match report, mode is 'llm' without warning suffix."""
    ctx = build_context(sample_congestion_report)
    obs_val = ctx["evidence"][0]["observed_value"]
    mock_reply = (
        f"Based on [E1], buffer queue saturation caused an observed value of {obs_val}. "
        "The primary root cause is Network Congestion."
    )

    with patch("copilot.explainer.ask_llm", return_value=mock_reply):
        res = ask_copilot(sample_congestion_report, "Explain the root cause")
        assert res.mode == "llm"
        assert "[E1]" in res.cited_evidence
        assert "⚠️ Note: some figures could not be verified" not in res.answer
        assert res.answer == mock_reply


def test_mocked_llm_unverified_response_appends_warning(sample_congestion_report):
    """When LLM API succeeds but invents numbers, mode is 'llm' and warning is appended."""
    mock_reply = "Packet loss peaked at 88.42% and delay reached 999.5ms on device-77."

    with patch("copilot.explainer.ask_llm", return_value=mock_reply):
        res = ask_copilot(sample_congestion_report, "What are the numbers?")
        assert res.mode == "llm"
        assert len(res.unverified_numbers) > 0
        assert "⚠️ Note: some figures could not be verified against the report." in res.answer


def test_ask_convenience_function(sample_congestion_report):
    """Convenience function ask() returns clean string answer."""
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
        answer_str = ask(sample_congestion_report, "Why this root cause?")
        assert isinstance(answer_str, str)
        assert len(answer_str) > 20


def test_api_ask_endpoint():
    """FastAPI endpoint POST /api/reports/{id}/ask works and returns structured response."""
    client = TestClient(app)
    diag_res = client.post("/api/diagnose", json={"scenario_id": "congestion"})
    assert diag_res.status_code == 200
    rep_id = diag_res.json()["report_id"]

    # Test asking about an existing report
    payload = {"question": "Why this root cause?"}
    res = client.post(f"/api/reports/{rep_id}/ask", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "answer" in data
    assert "mode" in data
    assert data["mode"] in ("llm", "fallback")
    assert "cited_evidence" in data
    assert isinstance(data["cited_evidence"], list)

    # Test asking about non-existent report
    bad_res = client.post("/api/reports/NON_EXISTENT_REP_9999/ask", json=payload)
    assert bad_res.status_code == 404
