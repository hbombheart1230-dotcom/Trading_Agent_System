import os
import pytest
from unittest.mock import patch
from libs.reporting.trade_report_ai import build_separated_ai_trade_report
from libs.reporting.daily_report import build_separated_daily_report
from libs.reporting.llm_daily_summary import summarize_daily_report_with_artifact
from libs.reporting.operator_visibility import build_separated_operator_brief
from libs.reporting.reporter_ai_review import build_ai_reporter_review
from graphs.nodes.strategist_node import _run_strategist_frame_llm

def test_reporting_roles_use_correct_env_vars(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL_TRADE_REPORT", "test/trade-model")
    monkeypatch.setenv("TRADE_REPORT_AI_MODEL", "legacy/trade-model")
    monkeypatch.setenv("OPENROUTER_MODEL_REPORTER_FINAL", "test/final-model")
    monkeypatch.setenv("REPORTER_AI_REVIEW_MODEL", "legacy/review-model")
    monkeypatch.setenv("DAILY_REPORT_LLM_MODEL", "legacy/daily-model")
    monkeypatch.setenv("OPENROUTER_MODEL_OPERATOR_UI", "test/ui-model")
    monkeypatch.setenv("OPENROUTER_DEFAULT_MODEL", "test/default-model")
    monkeypatch.setenv("DRY_RUN", "1")

    with patch("libs.reporting.fact_narrative_report.build_separated_report") as mock_report:
        build_separated_ai_trade_report("dummy/dir")
        assert mock_report.call_args[1]["model"] == "test/trade-model"

    with patch("libs.reporting.fact_narrative_report.build_separated_report") as mock_report:
        build_separated_daily_report({})
        assert mock_report.call_args[1]["model"] == "test/final-model"

    with patch("libs.reporting.fact_narrative_report.build_separated_report") as mock_report:
        build_separated_operator_brief("dir", "SYM", "root")
        assert mock_report.call_args[1]["model"] == "test/ui-model"

    _summary, artifact = summarize_daily_report_with_artifact(
        state={"eod_day": "2026-04-07"},
        policy={},
    )
    assert artifact["model"] == "test/final-model"


def test_trade_report_legacy_env_remains_fallback(monkeypatch):
    monkeypatch.delenv("OPENROUTER_MODEL_TRADE_REPORT", raising=False)
    monkeypatch.setenv("TRADE_REPORT_AI_MODEL", "legacy/trade-model")

    with patch("libs.reporting.fact_narrative_report.build_separated_report") as mock_report:
        build_separated_ai_trade_report("dummy/dir")
        assert mock_report.call_args[1]["model"] == "legacy/trade-model"


def test_reporter_final_review_prefers_canonical_env_over_legacy(monkeypatch):
    monkeypatch.setenv("REPORTER_AI_REVIEW_ENABLED", "1")
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.setenv("OPENROUTER_MODEL_REPORTER_FINAL", "test/final-model")
    monkeypatch.setenv("REPORTER_AI_REVIEW_MODEL", "legacy/review-model")

    captured = {}

    class FakeRoute:
        def __init__(self, model):
            self.model = model

    class FakeRouter:
        def __init__(self):
            self.client = True

        def resolve(self, role, policy=None):
            captured["resolved_role"] = role
            captured["policy"] = dict(policy or {})
            return FakeRoute(captured["policy"].get("model"))

        def chat(self, role, messages, policy=None):
            captured["chat_role"] = role
            captured["chat_policy"] = dict(policy or {})
            return (
                '{"ai_summary":"ok","ai_findings":[],"ai_root_causes":[],'
                '"ai_improvement_suggestions":[],"ai_run_grade":"A",'
                '"ai_agent_evaluations":{},"ai_evidence_links":{"findings":[],"root_causes":[],"improvements":[]}}'
            )

        @classmethod
        def from_env(cls):
            return cls()

    monkeypatch.setattr("libs.reporting.reporter_ai_review.LLMRouter", FakeRouter)
    monkeypatch.setattr("libs.reporting.reporter_ai_review.record_raw_input", lambda *args, **kwargs: None)
    monkeypatch.setattr("libs.reporting.reporter_ai_review.record_llm_prompt", lambda *args, **kwargs: None)
    monkeypatch.setattr("libs.reporting.reporter_ai_review.record_llm_response", lambda *args, **kwargs: None)

    out = build_ai_reporter_review(day="2026-04-07", reporter_output={})

    assert captured["resolved_role"] == "reporter_final"
    assert captured["policy"]["model"] == "test/final-model"
    assert captured["chat_policy"]["model"] == "test/final-model"
    assert out["model"] == "test/final-model"

def test_strategist_primary_fallback_trace(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_MODEL_PRIMARY", "primary/model")
    monkeypatch.setenv("AI_STRATEGIST_MODEL_FALLBACK", "fallback/model")
    monkeypatch.setenv("AI_STRATEGIST_RETRY_MAX", "1") # 1 primary + 1 fallback = 2 loops
    
    state = {"run_id": "test"}
    policy = {"strategist_frame_use_llm": True, "ai_strategist_provider": "api", "api_key": "test", "endpoint": "test"}
    
    class FailingRouter:
        client = True
        def chat(self, *args, **kwargs):
            raise Exception("Mock Network Error")
            
        @classmethod
        def from_env(cls):
            return cls()
            
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", FailingRouter)
    
    _, meta = _run_strategist_frame_llm(state=state, policy=policy, payload={})
    
    trace = meta.get("llm_call_trace", {})
    assert trace.get("primary_attempted") is True
    assert trace.get("primary_failed") is True
    assert trace.get("fallback_used") is True
    assert trace.get("final_model") == "fallback/model"
