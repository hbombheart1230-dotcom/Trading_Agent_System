from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from graphs.commander_runtime import _run_integrated_chain
from graphs.nodes.strategist_node import _run_strategist_frame_llm, strategist_node
from libs.llm.model_catalog import (
    resolve_execution_profile,
    resolve_model_profile,
    resolve_policy_llm_execution_slot,
)
from libs.reporting.daily_report import build_separated_daily_report
from libs.reporting.llm_daily_summary import summarize_daily_report_with_artifact
from libs.reporting.operator_visibility import build_separated_operator_brief
from libs.reporting.reporter_ai_review import build_ai_reporter_review
from libs.reporting.trade_report_ai import build_separated_ai_trade_report


def test_llm_profiles_resolve_expected_primary_and_fallback() -> None:
    fast = resolve_model_profile("fast_free")
    balanced = resolve_model_profile("balanced")
    strong = resolve_model_profile("strong_reasoning")

    assert fast["primary"] == "minimax/minimax-m2.5"
    assert fast["fallback"] == "deepseek/deepseek-v3.2"
    assert balanced["primary"] == "deepseek/deepseek-v3.2"
    assert balanced["fallback"] == "minimax/minimax-m2.5"
    assert strong["primary"] == "moonshotai/kimi-k2.5"
    assert strong["fallback"] == "deepseek/deepseek-v3.2"


def test_llm_execution_profiles_resolve_expected_defaults() -> None:
    baseline = resolve_execution_profile("default_intraday", default_profile="default_intraday")
    strategist = resolve_execution_profile("balanced_reasoning", default_profile="balanced_reasoning")
    intraday = resolve_execution_profile("concise_review", default_profile="concise_review")
    daily = resolve_execution_profile("deep_review", default_profile="deep_review")

    assert baseline["profile_name"] == "default_intraday"
    assert baseline["retry"]["max_attempts"] == 2
    assert baseline["retry"]["backoff_sec"] == 0.0
    assert strategist["temperature"] == 0.1
    assert strategist["max_tokens"] == 8192
    assert strategist["timeout_sec"] == 15
    assert strategist["retry_max"] == 2
    assert intraday["temperature"] == 0.2
    assert intraday["max_tokens"] == 8192
    assert daily["temperature"] == 0.2
    assert daily["max_tokens"] == 8192


def test_llm_model_env_keys_removed_from_env_example() -> None:
    text = Path("config/.env.example").read_text(encoding="utf-8")
    for key in (
        "AI_STRATEGIST_PROVIDER",
        "AI_STRATEGIST_MODEL_PRIMARY",
        "AI_STRATEGIST_MODEL_FALLBACK",
        "OPENROUTER_DEFAULT_MODEL",
        "OPENROUTER_MODEL_OPERATOR_UI",
        "OPENROUTER_MODEL_TRADE_REPORT",
        "OPENROUTER_MODEL_REPORTER_FINAL",
        "OPENROUTER_X_TITLE",
        "REPORTER_AI_REVIEW_TEMPERATURE",
        "REPORTER_AI_REVIEW_MAX_TOKENS",
        "AI_STRATEGIST_TIMEOUT_SEC",
        "AI_STRATEGIST_MAX_TOKENS",
        "AI_STRATEGIST_RETRY_MAX",
        "OPENROUTER_DEFAULT_TEMPERATURE",
        "OPENROUTER_DEFAULT_MAX_TOKENS",
    ):
        assert key not in text, key


def test_commander_injects_llm_profiles_into_applied_policy(monkeypatch) -> None:
    def fake_build_portfolio_snapshot(state):
        state["portfolio_snapshot"] = {"cash": 1_000_000.0, "positions": [], "_health": {"reader_ok": True}}
        return state

    def fake_build_risk_context(state):
        return state

    def fake_strategist(state):
        state["strategist_output"] = {"playbook": "pullback"}
        return state

    def fake_scanner(state):
        state["selected"] = {"symbol": "005930"}
        return state

    def fake_monitor(state):
        state["intents"] = []
        return state

    def fake_decision(state):
        state["decision"] = "hold"
        return state

    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_build_portfolio_snapshot)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_build_risk_context)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)

    out = _run_integrated_chain({}, execute_fn=lambda state: state)
    llm_policy = ((out.get("applied_policy") or {}).get("llm") or {})
    commander_decision = out.get("commander_decision") or {}

    top_level_exec = llm_policy.get("execution_profile") or {}
    assert top_level_exec.get("profile_name") == "default_intraday"
    assert top_level_exec.get("temperature") == 0.2
    assert top_level_exec.get("max_tokens") == 8192
    assert top_level_exec.get("timeout_sec") == 15
    assert (top_level_exec.get("retry") or {}).get("max_attempts") == 2
    assert (top_level_exec.get("retry") or {}).get("backoff_sec") == 0.0
    assert ((llm_policy.get("strategist") or {}).get("profile")) == "balanced"
    assert ((llm_policy.get("strategist") or {}).get("primary")) == "deepseek/deepseek-v3.2"
    assert ((llm_policy.get("strategist") or {}).get("fallback")) == "minimax/minimax-m2.5"
    strategist_exec = ((llm_policy.get("strategist") or {}).get("execution_profile")) or {}
    assert strategist_exec.get("name") == "balanced_reasoning"
    assert strategist_exec.get("max_tokens") == 8192
    assert strategist_exec.get("timeout_sec") == 15
    assert strategist_exec.get("retry_max") == 2
    assert ((((llm_policy.get("reporter") or {}).get("intraday") or {}).get("profile"))) == "fast_free"
    assert ((((llm_policy.get("reporter") or {}).get("intraday") or {}).get("primary"))) == "minimax/minimax-m2.5"
    intraday_exec = ((((llm_policy.get("reporter") or {}).get("intraday") or {}).get("execution_profile")) or {})
    assert intraday_exec.get("name") == "concise_review"
    assert intraday_exec.get("max_tokens") == 8192
    assert ((((llm_policy.get("reporter") or {}).get("daily") or {}).get("profile"))) == "strong_reasoning"
    assert ((((llm_policy.get("reporter") or {}).get("daily") or {}).get("primary"))) == "moonshotai/kimi-k2.5"
    daily_exec = ((((llm_policy.get("reporter") or {}).get("daily") or {}).get("execution_profile")) or {})
    assert daily_exec.get("name") == "deep_review"
    assert daily_exec.get("max_tokens") == 8192
    assert commander_decision.get("llm_policy_source") == "commander_applied_policy"
    assert commander_decision.get("llm_execution_profile_source") == "commander_applied_policy"


def test_top_level_execution_profile_is_canonical_over_role_specific_slot() -> None:
    execution_slot = resolve_policy_llm_execution_slot(
        {
            "applied_policy": {
                "llm": {
                    "execution_profile": {
                        "profile_name": "default_intraday",
                        "temperature": 0.25,
                        "max_tokens": 2048,
                        "timeout_sec": 11,
                        "retry": {"max_attempts": 4, "backoff_sec": 0.2},
                    },
                    "strategist": {
                        "execution_profile": {
                            "name": "balanced_reasoning",
                            "temperature": 0.1,
                            "max_tokens": 8192,
                            "timeout_sec": 15,
                            "retry_max": 2,
                        }
                    },
                }
            }
        },
        "strategist",
        default_profile="balanced_reasoning",
        defaults={
            "profile_name": "balanced_reasoning",
            "name": "balanced_reasoning",
            "temperature": 0.1,
            "max_tokens": 8192,
            "timeout_sec": 15,
            "retry": {"max_attempts": 2, "backoff_sec": 0.0},
        },
    )

    assert execution_slot.get("profile_name") == "default_intraday"
    assert execution_slot.get("temperature") == 0.25
    assert execution_slot.get("max_tokens") == 2048
    assert execution_slot.get("timeout_sec") == 11
    assert execution_slot.get("policy_source") == "applied_policy.llm.execution_profile"
    assert (execution_slot.get("retry") or {}).get("max_attempts") == 4
    assert (execution_slot.get("retry") or {}).get("backoff_sec") == 0.2


def test_reporting_roles_use_applied_policy_models(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")

    with patch("libs.reporting.trade_read_model.build_trade_read_model", return_value={"applied_policy": {"llm": {"reporter": {"intraday": {"primary": "minimax/minimax-m2.5"}}}}}), patch(
        "libs.reporting.fact_narrative_report.build_separated_report"
    ) as mock_report:
        build_separated_ai_trade_report("dummy/dir")
        assert mock_report.call_args[1]["model"] == "minimax/minimax-m2.5"

    with patch("libs.reporting.fact_narrative_report.build_separated_report") as mock_report:
        build_separated_daily_report(
            {
                "applied_policy": {
                    "llm": {
                        "reporter": {"daily": {"primary": "moonshotai/kimi-k2.5"}},
                        "execution_profile": {"profile_name": "default_intraday", "max_tokens": 1444},
                    }
                }
            }
        )
        assert mock_report.call_args[1]["model"] == "moonshotai/kimi-k2.5"
        assert mock_report.call_args[1]["execution_profile"]["profile_name"] == "default_intraday"

    with patch("libs.reporting.trade_read_model.build_trade_read_model", return_value={"applied_policy": {"llm": {"reporter": {"intraday": {"primary": "minimax/minimax-m2.5"}}}}}), patch(
        "libs.reporting.symbol_read_model.build_symbol_read_model", return_value={}
    ), patch("libs.reporting.fact_narrative_report.build_separated_report") as mock_report:
        build_separated_operator_brief("dir", "SYM", "root")
        assert mock_report.call_args[1]["model"] == "minimax/minimax-m2.5"
        assert mock_report.call_args[1]["execution_profile"]["profile_name"] in {"default_intraday", "concise_review"}

    with patch("libs.reporting.trade_read_model.build_trade_read_model", return_value={"trade_id": "TRD_1"}), patch(
        "libs.reporting.symbol_read_model.build_symbol_read_model", return_value={"applied_policy": {"llm": {"reporter": {"intraday": {"primary": "openrouter/symbol-model"}}}}}
    ), patch("libs.reporting.fact_narrative_report.build_separated_report") as mock_report:
        build_separated_operator_brief("dir", "SYM", "root")
        assert mock_report.call_args[1]["model"] == "openrouter/symbol-model"

    _summary, artifact = summarize_daily_report_with_artifact(
        state={"eod_day": "2026-04-07", "applied_policy": {"llm": {"reporter": {"daily": {"primary": "moonshotai/kimi-k2.5"}}}}},
        policy={},
    )
    assert artifact["model"] == "moonshotai/kimi-k2.5"


def test_reporter_final_review_prefers_applied_policy_profile_model(monkeypatch):
    monkeypatch.delenv("DRY_RUN", raising=False)

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

    out = build_ai_reporter_review(
        day="2026-04-07",
        reporter_output={
            "applied_policy": {
                "reporter": {"ai_review": {"enabled": True}},
                "llm": {
                    "reporter": {
                        "daily": {
                            "primary": "moonshotai/kimi-k2.5",
                            "execution_profile": {
                                "name": "deep_review",
                                "temperature": 0.25,
                                "max_tokens": 4096,
                            },
                        }
                    }
                },
            }
        },
    )

    assert captured["resolved_role"] == "reporter_final"
    assert captured["policy"]["model"] == "moonshotai/kimi-k2.5"
    assert captured["policy"]["temperature"] == 0.25
    assert captured["policy"]["max_tokens"] == 4096
    assert captured["chat_policy"]["model"] == "moonshotai/kimi-k2.5"
    assert out["model"] == "moonshotai/kimi-k2.5"


def test_reporter_final_review_uses_env_execution_fallback_when_policy_missing(monkeypatch):
    monkeypatch.delenv("DRY_RUN", raising=False)
    monkeypatch.setenv("REPORTER_AI_REVIEW_TEMPERATURE", "0.45")
    monkeypatch.setenv("REPORTER_AI_REVIEW_MAX_TOKENS", "1536")

    captured = {}

    class FakeRoute:
        def __init__(self, model):
            self.model = model

    class FakeRouter:
        def __init__(self):
            self.client = True

        def resolve(self, role, policy=None):
            captured["policy"] = dict(policy or {})
            return FakeRoute(captured["policy"].get("model"))

        def chat(self, role, messages, policy=None):
            captured["chat_policy"] = dict(policy or {})
            return (
                '{"ai_summary":"ok","ai_findings":["f"],"ai_root_causes":["r"],'
                '"ai_improvement_suggestions":["i"],"ai_run_grade":"A",'
                '"ai_agent_evaluations":{},"ai_evidence_links":{"findings":[],"root_causes":[],"improvements":[]}}'
            )

        @classmethod
        def from_env(cls):
            return cls()

    monkeypatch.setattr("libs.reporting.reporter_ai_review.LLMRouter", FakeRouter)
    monkeypatch.setattr("libs.reporting.reporter_ai_review.record_raw_input", lambda *args, **kwargs: None)
    monkeypatch.setattr("libs.reporting.reporter_ai_review.record_llm_prompt", lambda *args, **kwargs: None)
    monkeypatch.setattr("libs.reporting.reporter_ai_review.record_llm_response", lambda *args, **kwargs: None)

    out = build_ai_reporter_review(
        day="2026-04-09",
        reporter_output={
            "applied_policy": {
                "reporter": {"ai_review": {"enabled": True}},
                "llm": {"reporter": {"daily": {"primary": "moonshotai/kimi-k2.5"}}},
            }
        },
    )

    assert float(captured["policy"]["temperature"]) == 0.45
    assert int(captured["policy"]["max_tokens"]) == 1536
    assert out["llm_execution_profile_source"] == "fallback_env"
    assert float((out["llm_execution_effective_config"] or {}).get("temperature") or 0.0) == 0.45
    assert int((out["llm_execution_effective_config"] or {}).get("max_tokens") or 0) == 1536


def test_strategist_primary_fallback_trace_reads_policy_models(monkeypatch):
    state = {"run_id": "test"}
    policy = {
        "strategist_frame_use_llm": True,
        "ai_strategist_provider": "api",
        "api_key": "test",
        "endpoint": "test",
        "applied_policy": {
            "llm": {
                "strategist": {
                    "profile": "balanced",
                    "primary": "deepseek/deepseek-v3.2",
                    "fallback": "minimax/minimax-m2.5",
                    "execution_profile": {"name": "balanced_reasoning", "retry_max": 1},
                }
            }
        },
    }

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
    assert trace.get("final_model") == "minimax/minimax-m2.5"


def test_strategist_policy_model_keeps_decision_surface_unchanged(monkeypatch):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions")

    class FakeRouter:
        def __init__(self):
            self.client = object()

        @classmethod
        def from_env(cls):
            return cls()

        def resolve(self, role, *, policy=None):
            class _Route:
                model = str((policy or {}).get("model") or "deepseek/deepseek-v3.2")

            return _Route()

        def chat(self, role, messages, *, policy=None):
            return (
                '{"market_regime":"risk_on","market_sentiment":"bullish","themes":["semiconductor","ai"],'
                '"avoid_themes":["high_gap_speculative"],"playbook":"breakout","scanner_bias":"momentum",'
                '"scanner_priority":["momentum","trend_strength","trading_value"],'
                '"trade_aggressiveness":"high","risk_tone":"aggressive","monitor_guidance":"hold_through_noise",'
                '"report_focus":["theme_accuracy","exit_quality"]}'
            )

    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", FakeRouter)
    state = {
        "run_id": "strategist-llm-policy-test",
        "themes": ["legacy_theme"],
        "candidate_symbols": ["005930", "000660", "035420"],
        "policy": {
            "use_global_sentiment": False,
            "use_news_analysis": False,
            "use_universe_builder": False,
            "applied_policy": {
                "llm": {
                    "strategist": {
                        "profile": "balanced",
                        "primary": "deepseek/deepseek-v3.2",
                        "fallback": "minimax/minimax-m2.5",
                    }
                }
            },
        },
    }

    out = strategist_node(state)
    strategist_output = out.get("strategist_output") or {}
    strategist_llm = out.get("strategist_llm") or {}

    assert strategist_output.get("themes") == ["semiconductor", "ai"]
    assert strategist_output.get("playbook") == "breakout"
    assert strategist_output.get("risk_tone") == "aggressive"
    assert strategist_output.get("monitor_guidance") == "hold_through_noise"
    assert strategist_llm.get("status") == "ok"
