import os
import pytest
from unittest.mock import patch
from libs.reporting.trade_report_ai import build_separated_ai_trade_report
from libs.reporting.daily_report import build_separated_daily_report
from libs.reporting.operator_visibility import build_separated_operator_brief
from graphs.nodes.strategist_node import _run_strategist_frame_llm

def test_reporting_roles_use_correct_env_vars(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL_TRADE_REPORT", "test/trade-model")
    monkeypatch.setenv("OPENROUTER_MODEL_REPORTER_FINAL", "test/final-model")
    monkeypatch.setenv("OPENROUTER_MODEL_OPERATOR_UI", "test/ui-model")
    monkeypatch.setenv("DRY_RUN", "1")

    with patch("libs.reporting.trade_report_ai.build_separated_report") as mock_report:
        build_separated_ai_trade_report("dummy/dir")
        assert mock_report.call_args[1]["model"] == "test/trade-model"

    with patch("libs.reporting.daily_report.build_separated_report") as mock_report:
        build_separated_daily_report({})
        assert mock_report.call_args[1]["model"] == "test/final-model"

    with patch("libs.reporting.operator_visibility.build_separated_report") as mock_report:
        build_separated_operator_brief("dir", "SYM", "root")
        assert mock_report.call_args[1]["model"] == "test/ui-model"

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