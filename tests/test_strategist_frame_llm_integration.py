from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List
import json

import pytest

from graphs.nodes.strategist_node import (
    _build_commander_context_summary,
    _build_compact_strategist_llm_payload,
    _build_strategist_llm_messages,
    strategist_node,
)
from libs.research.strategy_memory_store import save_strategy_feedback


@pytest.fixture(autouse=True)
def _default_strategist_llm_env(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://openrouter.ai/api/v1/chat/completions")


class _MemoryLogger:
    def __init__(self) -> None:
        self.rows: List[Dict[str, Any]] = []

    def log(self, run_id: str, stage: str, event: str, payload: Dict[str, Any]) -> None:
        self.rows.append(
            {
                "run_id": str(run_id),
                "stage": str(stage),
                "event": str(event),
                "payload": dict(payload or {}),
            }
        )


@dataclass
class _Route:
    model: str


class _FakeRouterOk:
    def __init__(self) -> None:
        self.client = object()

    @staticmethod
    def from_env() -> "_FakeRouterOk":
        return _FakeRouterOk()

    def resolve(self, role: str, *, policy: Dict[str, Any] | None = None) -> _Route:
        return _Route(model=str((policy or {}).get("model") or "minimax/minimax-m2.5"))

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        return (
            '{"market_regime":"risk_on","market_sentiment":"bullish","themes":["semiconductor","ai"],'
            '"avoid_themes":["high_gap_speculative"],"playbook":"breakout","scanner_bias":"momentum",'
            '"tactical_strategy":"opening_range_breakout",'
            '"strategy_scores":{"opening_range_breakout":0.82,"vwap_reclaim_pullback":0.61,"defensive_observe":0.14},'
            '"rejected_strategy_reasons":{"defensive_observe":"risk_on tape supports active watch"},'
            '"candidate_watch_policy":{"max_priority_rank":7,"max_runner_ups":4,"cascade_enabled":true,'
            '"cascade_allowed_reasons":["too_extended_from_vwap","breakout_not_ready"],'
            '"cascade_blocked_reasons":["cost_filter_failed","risk_policy_block"],'
            '"reason":"breakout tape supports scanning beyond rank one"},'
            '"scanner_priority":["momentum","trend_strength","trading_value"],'
            '"trade_aggressiveness":"high","risk_tone":"aggressive","monitor_guidance":"hold_through_noise",'
            '"report_focus":["theme_accuracy","exit_quality"]}'
        )


class _FakeRouterBadJson(_FakeRouterOk):
    @staticmethod
    def from_env() -> "_FakeRouterBadJson":
        return _FakeRouterBadJson()

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        return "not-json-response"


class _FakeRouterEmpty(_FakeRouterOk):
    @staticmethod
    def from_env() -> "_FakeRouterEmpty":
        return _FakeRouterEmpty()

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        return ""


class _FakeRouterTruncatedJson(_FakeRouterOk):
    @staticmethod
    def from_env() -> "_FakeRouterTruncatedJson":
        return _FakeRouterTruncatedJson()

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        return '{"market_regime":"risk_off","themes":["defensive"],"playbook":"defensive"'


class _FakeRouterRepairSuccess(_FakeRouterOk):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    @staticmethod
    def from_env() -> "_FakeRouterRepairSuccess":
        return _FakeRouterRepairSuccess()

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        self.calls += 1
        if self.calls == 1:
            return "not-json-response"
        return (
            '{"market_regime":"risk_on","market_sentiment":"bullish","themes":["semiconductor"],'
            '"avoid_themes":["high_gap_speculative"],"playbook":"breakout","scanner_bias":"momentum",'
            '"scanner_priority":["momentum","trend_strength"],'
            '"trade_aggressiveness":"high","risk_tone":"aggressive","monitor_guidance":"hold_through_noise",'
            '"report_focus":["theme_accuracy","exit_quality"]}'
        )


class _FakeRouterNestedJson(_FakeRouterOk):
    @staticmethod
    def from_env() -> "_FakeRouterNestedJson":
        return _FakeRouterNestedJson()

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        return (
            '{"output":{"market_regime":"risk_off","market_sentiment":"bearish",'
            '"themes":"defensive_large_cap, semiconductors_hbm",'
            '"avoid_themes":"high_gap_speculative",'
            '"playbook":"pullback","scanner_bias":"leader",'
            '"scanner_priority":"trading_value, trend_strength",'
            '"trade_aggressiveness":"low","risk_tone":"conservative",'
            '"monitor_guidance":"defensive_exit","report_focus":"theme_accuracy|exit_quality"}}'
        )


class _FakeRouterProseContract(_FakeRouterOk):
    @staticmethod
    def from_env() -> "_FakeRouterProseContract":
        return _FakeRouterProseContract()

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        return (
            "Let me analyze the input and produce the strategist frame.\n\n"
            "1. **market_regime**: the safest fit is \"risk_off\"\n"
            "2. **market_sentiment**: use \"bearish\"\n"
            "3. **themes**: [\"defensive_assets\", \"broad_market_leaders\"]\n"
            "4. **avoid_themes**: [\"high_beta\", \"small_cap_speculative\"]\n"
            "5. **playbook**: \"defensive\"\n"
            "6. **scanner_bias**: \"large_cap\"\n"
            "7. **scanner_priority**: [\"trading_value\", \"leader_quality\", \"trend_strength\"]\n"
            "8. **trade_aggressiveness**: \"low\"\n"
            "9. **risk_tone**: \"conservative\"\n"
            "10. **monitor_guidance**: \"defensive_exit\"\n"
            "11. **report_focus**: [\"theme_accuracy\", \"exit_quality\"]\n"
        )


class _FakeRouterCapturePolicy(_FakeRouterOk):
    last_policy: Dict[str, Any] | None = None

    @staticmethod
    def from_env() -> "_FakeRouterCapturePolicy":
        _FakeRouterCapturePolicy.last_policy = None
        return _FakeRouterCapturePolicy()

    def resolve(self, role: str, *, policy: Dict[str, Any] | None = None) -> _Route:
        _FakeRouterCapturePolicy.last_policy = dict(policy or {})
        return _Route(model=str((policy or {}).get("model") or "minimax/minimax-m2.5"))

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        _FakeRouterCapturePolicy.last_policy = dict(policy or {})
        return super().chat(role, messages, policy=policy)


class _FakeRouterHintOnlyProse(_FakeRouterOk):
    @staticmethod
    def from_env() -> "_FakeRouterHintOnlyProse":
        return _FakeRouterHintOnlyProse()

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        return (
            "The market context suggests caution.\n"
            "market_regime_hint: \"neutral\"\n"
            "market_sentiment_hint: \"neutral\"\n"
            "playbook_hint: \"pullback\"\n"
            "themes_hint: [\"broad_market_leaders\"]\n"
            "key_events_hint: [\"global_sentiment score=-0.170\"]\n"
        )


class _FakeRouterThemeConstraint(_FakeRouterOk):
    @staticmethod
    def from_env() -> "_FakeRouterThemeConstraint":
        return _FakeRouterThemeConstraint()

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        return (
            '{"market_regime":"risk_on","market_sentiment":"bullish",'
            '"themes":["invented_theme","semiconductor"],'
            '"selected_themes":["invented_theme","battery"],'
            '"theme_strategy":{"selection_mode":"kiwoom_api_constrained","selected_themes":['
            '{"theme":"invented_theme","playbook_overlay":"momentum","scanner_directive":"rank components","reason":"bad"},'
            '{"theme":"battery","playbook_overlay":"momentum","scanner_directive":"rank components","reason":"valid"}]},'
            '"avoid_themes":["high_gap_speculative"],"playbook":"breakout","scanner_bias":"momentum",'
            '"scanner_priority":["momentum","trend_strength","trading_value"],'
            '"trade_aggressiveness":"high","risk_tone":"aggressive","monitor_guidance":"hold_through_noise",'
            '"report_focus":["theme_accuracy","exit_quality"]}'
        )


class _FakeRouterStage2SelectedSymbol(_FakeRouterOk):
    @staticmethod
    def from_env() -> "_FakeRouterStage2SelectedSymbol":
        return _FakeRouterStage2SelectedSymbol()

    def chat(self, role: str, messages: List[Dict[str, Any]], *, policy: Dict[str, Any] | None = None) -> str:
        return json.dumps(
            {
                "selected_symbol_decision": "cascade_to_runner_up",
                "target_symbol": "005930",
                "target_rank": 1,
                "runner_up_order": ["000660", "035420"],
                "monitor_instruction": {
                    "watch_intensity": "strict",
                    "required_confirmations": ["vwap_reclaim", "net_cost_hurdle_pass"],
                    "avoid_if": ["opening_gap_chase_without_pullback"],
                },
                "entry_policy_delta": {
                    "tighten_confidence_threshold": True,
                    "require_prev_close_context": True,
                    "require_cost_hurdle": True,
                },
                "memory_usage": {
                    "status": "used",
                    "sample_count": 4,
                    "confidence": "medium",
                    "data_quality": "ok",
                    "effect": "cautionary",
                    "reason": "최근 동일 종목은 추격 진입 비용 손실이 반복되었습니다.",
                },
                "commander_actionability": "policy_delta_allowed",
                "confidence": 0.72,
                "reason": "1순위는 비용 장벽과 갭 추격 리스크가 있어 차순위 cascade 감시가 낫습니다.",
            },
            ensure_ascii=False,
        )


def _base_state(logger: _MemoryLogger) -> Dict[str, Any]:
    return {
        "run_id": "strategist-llm-test",
        "event_logger": logger,
        "themes": ["legacy_theme"],
        "candidate_symbols": ["005930", "000660", "035420"],
        "policy": {
            "use_global_sentiment": False,
            "use_news_analysis": False,
            "use_universe_builder": False,
        },
    }


def test_strategist_frame_llm_overrides_are_applied(monkeypatch):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("AI_STRATEGIST_MODEL", "minimax/minimax-m2.5")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterOk)

    logger = _MemoryLogger()
    out = strategist_node(_base_state(logger))

    strategist_output = out.get("strategist_output") or {}
    assert strategist_output.get("themes") == ["semiconductor", "ai"]
    assert strategist_output.get("playbook") == "breakout"
    assert strategist_output.get("scanner_bias") == "momentum"
    assert strategist_output.get("risk_tone") == "aggressive"
    assert strategist_output.get("monitor_guidance") == "hold_through_noise"
    assert strategist_output.get("pre_llm_playbook")
    assert strategist_output.get("llm_requested_playbook") == "breakout"
    assert strategist_output.get("requested_playbook") == "breakout"
    assert strategist_output.get("requested_playbook_source") == "llm"
    assert strategist_output.get("final_playbook") == "breakout"
    assert strategist_output.get("tactical_strategy") == "opening_range_breakout"
    assert strategist_output.get("strategy_scores", {}).get("opening_range_breakout") == 0.82
    assert strategist_output.get("rejected_strategy_reasons", {}).get("defensive_observe") == "risk_on tape supports active watch"
    watch_policy = strategist_output.get("candidate_watch_policy") or {}
    assert watch_policy.get("behavior_effect") == "visibility_only"
    assert watch_policy.get("max_priority_rank") == 7
    assert watch_policy.get("max_runner_ups") == 4
    assert (strategist_output.get("strategy_policy") or {}).get("scanner_policy", {}).get("candidate_watch_policy") == watch_policy
    assert bool(strategist_output.get("llm_frame_applied")) is True
    assert str(strategist_output.get("llm_frame_status") or "") == "ok"

    strategist_llm = out.get("strategist_llm") or {}
    assert strategist_llm.get("status") == "ok"
    assert strategist_llm.get("applied") is True
    assert "semiconductor" in list(out.get("theme_map", {}).keys())
    assert "ai" in list(out.get("sector_map", {}).keys())
    assert out.get("theme_map", {}).get("semiconductor") == ["005930", "000660", "035420"]
    llm_rows = [r for r in logger.rows if r.get("stage") == "strategist_llm" and r.get("event") == "result"]
    assert len(llm_rows) == 1
    assert bool((llm_rows[0].get("payload") or {}).get("ok")) is True


def test_strategist_selected_themes_are_constrained_to_kiwoom_available_themes(monkeypatch):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("AI_STRATEGIST_MODEL", "minimax/minimax-m2.5")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterThemeConstraint)

    logger = _MemoryLogger()
    state = _base_state(logger)
    state["mock_theme_groups"] = [
        {
            "thema_grp_cd": "400",
            "thema_nm": "semiconductor",
            "stk_num": "5",
            "flu_rt": "+4.0",
            "rising_stk_num": "4",
            "fall_stk_num": "0",
            "dt_prft_rt": "+12.0",
        },
        {
            "thema_grp_cd": "401",
            "thema_nm": "battery",
            "stk_num": "5",
            "flu_rt": "+3.0",
            "rising_stk_num": "3",
            "fall_stk_num": "1",
            "dt_prft_rt": "+8.0",
        },
    ]
    state["mock_theme_component_map"] = {
        "semiconductor": ["005930", "000660"],
        "battery": ["373220"],
    }

    out = strategist_node(state)
    strategist_output = out.get("strategist_output") or {}

    assert "invented_theme" not in strategist_output.get("selected_themes")
    assert strategist_output.get("selected_themes")[:2] == ["battery", "semiconductor"]
    assert strategist_output.get("theme_strategy", {}).get("selection_mode") == "kiwoom_api_constrained"
    assert out.get("scanner_guidance", {}).get("selected_themes")[:2] == ["battery", "semiconductor"]


def test_build_commander_context_summary_recomputes_stale_daily_memory_from_state() -> None:
    state = {
        "day": "2026-04-24",
        "runtime_phase": "session",
        "strategy_memory": {
            "status": "ok",
            "requested_day": "2026-04-24",
            "resolved_day": "2026-04-17",
            "day": "2026-04-17",
            "best_playbooks": ["defensive"],
            "worst_playbooks": ["defensive"],
            "recent_failures": ["playbook:defensive"],
            "recent_success_patterns": [],
            "playbook_performance_snapshot": {
                "defensive": {
                    "usage_count": 1,
                    "win_rate": 0.0,
                }
            },
            "market_condition_bias": {
                "preferred_risk_posture": "defensive",
                "system_health": "RED",
                "avg_monitor_only_ratio": 0.7994,
            },
        },
    }
    commander_decision = {
        "market_regime": "neutral",
        "session_bias": "active_selection",
        "risk_mode": "defensive",
        "memory_packets": {
            "daily_strategy_memory": {
                "status": "ok",
                "active": True,
                "requested_day": "2026-04-24",
                "resolved_day": "2026-04-17",
            }
        },
        "commander_memory_policy": {
            "application_mode": "surface_only",
            "active_layers": ["daily"],
            "scanner_bias_enabled": True,
            "monitor_bias_enabled": True,
        },
        "scanner_memory_bias": {
            "enabled": True,
            "active_layers": ["daily"],
            "source_weight_delta": {"top_value": 0.02},
        },
        "scanner_memory_bias_summary": {
            "enabled": True,
            "active_layers": ["daily"],
        },
        "monitor_memory_bias": {
            "enabled": True,
            "active_layers": ["daily"],
            "entry_policy_delta": {"max_extended_from_vwap_pct": -0.01},
        },
        "monitor_memory_bias_summary": {
            "enabled": True,
            "active_layers": ["daily"],
        },
    }

    context = _build_commander_context_summary(
        state=state,
        commander_decision=commander_decision,
        runtime_phase="session",
        market_regime="neutral",
        playbook="defensive",
    )

    assert context["memory_packets"]["daily_strategy_memory"]["requested_day"] == "2026-04-24"
    assert context["memory_packets"]["daily_strategy_memory"]["resolved_day"] == "2026-04-17"
    assert context["memory_packets"]["daily_strategy_memory"]["active"] is False
    assert context["commander_memory_policy"]["active_layers"] == []
    assert context["commander_memory_policy"]["scanner_bias_enabled"] is False
    assert context["scanner_memory_bias"]["enabled"] is False
    assert context["scanner_memory_bias_summary"]["enabled"] is False
    assert context["monitor_memory_bias"]["enabled"] is False
    assert context["monitor_memory_bias_summary"]["enabled"] is False


def test_strategist_frame_llm_parse_error_falls_back_to_deterministic(monkeypatch):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterBadJson)

    logger = _MemoryLogger()
    out = strategist_node(_base_state(logger))

    strategist_output = out.get("strategist_output") or {}
    assert strategist_output.get("playbook") in ("breakout", "pullback", "reversal", "defensive")
    assert bool(strategist_output.get("llm_frame_applied")) is False
    assert str(strategist_output.get("llm_frame_status") or "") == "parse_error"

    strategist_llm = out.get("strategist_llm") or {}
    assert strategist_llm.get("status") == "parse_error"
    assert strategist_llm.get("applied") is False
    assert strategist_llm.get("reason") == "strategist_llm_response_not_json"
    assert strategist_llm.get("attempts") == 3
    assert strategist_llm.get("repair_used") is True
    assert strategist_llm.get("blocked") is True
    assert strategist_llm.get("blocked_reason") == "strategist_llm_failed"


def test_strategist_frame_llm_empty_response_is_classified(monkeypatch):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterEmpty)

    logger = _MemoryLogger()
    out = strategist_node(_base_state(logger))

    strategist_output = out.get("strategist_output") or {}
    assert bool(strategist_output.get("llm_frame_applied")) is False
    assert str(strategist_output.get("llm_frame_status") or "") == "parse_error"

    strategist_llm = out.get("strategist_llm") or {}
    assert strategist_llm.get("status") == "parse_error"
    assert strategist_llm.get("reason") == "strategist_llm_response_empty"
    assert strategist_llm.get("attempts") == 3
    assert strategist_llm.get("repair_used") is True


def test_strategist_frame_llm_truncated_json_is_classified(monkeypatch):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterTruncatedJson)

    logger = _MemoryLogger()
    out = strategist_node(_base_state(logger))

    strategist_output = out.get("strategist_output") or {}
    assert bool(strategist_output.get("llm_frame_applied")) is False
    assert str(strategist_output.get("llm_frame_status") or "") == "parse_error"

    strategist_llm = out.get("strategist_llm") or {}
    assert strategist_llm.get("status") == "parse_error"
    assert strategist_llm.get("reason") == "strategist_llm_response_truncated_json"
    assert strategist_llm.get("attempts") == 3
    assert strategist_llm.get("repair_used") is True


def test_strategist_frame_llm_repair_retry_can_recover(monkeypatch):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterRepairSuccess)

    logger = _MemoryLogger()
    out = strategist_node(_base_state(logger))

    strategist_output = out.get("strategist_output") or {}
    assert strategist_output.get("themes") == ["semiconductor"]
    assert strategist_output.get("playbook") == "breakout"
    assert strategist_output.get("llm_frame_applied") is True
    assert strategist_output.get("llm_frame_status") == "ok"
    assert strategist_output.get("llm_frame_low_confidence") is True

    strategist_llm = out.get("strategist_llm") or {}
    assert strategist_llm.get("status") == "ok"
    assert strategist_llm.get("attempts") == 2
    assert strategist_llm.get("repair_used") is True
    assert strategist_llm.get("low_confidence") is True


def test_strategist_frame_llm_nested_output_and_string_lists_are_normalized(monkeypatch):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterNestedJson)

    logger = _MemoryLogger()
    out = strategist_node(_base_state(logger))

    strategist_output = out.get("strategist_output") or {}
    assert strategist_output.get("market_regime") == "risk_off"
    assert strategist_output.get("themes") == ["defensive_large_cap", "semiconductors_hbm"]
    avoid_themes = strategist_output.get("avoid_themes") or []
    assert "high_gap_speculative" in avoid_themes
    scanner_priority = strategist_output.get("scanner_priority") or []
    assert "trading_value" in scanner_priority
    assert "trend_strength" in scanner_priority
    report_focus = strategist_output.get("report_focus") or []
    assert "theme_accuracy" in report_focus
    assert "exit_quality" in report_focus
    assert strategist_output.get("llm_frame_applied") is True
    assert strategist_output.get("llm_frame_low_confidence") is False


def test_strategist_frame_llm_prose_contract_is_salvaged(monkeypatch):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterProseContract)

    logger = _MemoryLogger()
    out = strategist_node(_base_state(logger))

    strategist_output = out.get("strategist_output") or {}
    assert strategist_output.get("market_regime") == "risk_off"
    assert strategist_output.get("market_sentiment") == "bearish"
    assert strategist_output.get("playbook") == "defensive"
    assert strategist_output.get("scanner_bias") == "large_cap"
    assert strategist_output.get("monitor_guidance") == "defensive_exit"
    assert strategist_output.get("themes") == ["defensive_assets", "broad_market_leaders"]
    assert strategist_output.get("llm_frame_applied") is True
    assert strategist_output.get("llm_frame_status") == "ok"
    assert strategist_output.get("llm_frame_recovery_method") == "prose_contract"

    strategist_llm = out.get("strategist_llm") or {}
    assert strategist_llm.get("status") == "ok"
    assert strategist_llm.get("recovery_method") == "prose_contract"


def test_strategist_frame_llm_hint_only_prose_is_salvaged(monkeypatch):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterHintOnlyProse)

    logger = _MemoryLogger()
    out = strategist_node(_base_state(logger))

    strategist_output = out.get("strategist_output") or {}
    assert strategist_output.get("market_regime") == "neutral"
    assert strategist_output.get("market_sentiment") == "neutral"
    assert strategist_output.get("playbook") == "pullback"
    assert strategist_output.get("themes") == ["broad_market_leaders"]
    assert strategist_output.get("llm_frame_applied") is True
    assert strategist_output.get("llm_frame_status") == "ok"
    assert strategist_output.get("llm_frame_recovery_method") == "prose_contract"


def test_strategist_reads_recent_strategy_feedback_when_available(monkeypatch, tmp_path):
    memory_path = tmp_path / "strategy_memory" / "feedback.jsonl"
    save_strategy_feedback(
        "reporter-2026-03-10",
        {
            "day": "2026-03-10",
            "strategy_frame_summary": {
                "theme_top": {"semiconductor": 1},
                "playbook_top": {"breakout": 1},
                "risk_tone_top": {"aggressive": 1},
                "monitor_guidance_top": {"hold_through_noise": 1},
                "report_focus_top": {"theme_accuracy": 1},
            },
            "strategist_evaluation": {
                "themes_proposed": ["semiconductor"],
                "theme_alignment_status": "aligned",
                "assessment": "aligned",
            },
            "scanner_evaluation": {
                "candidate_source_top": {"kiwoom_market_data": 1},
                "selection_status": "stable",
                "assessment": "ok",
                "no_candidate_total": 0,
            },
            "monitor_evaluation": {
                "monitor_status": "stable",
                "monitor_reason_top": {"hold": 1},
                "rapid_buy_sell_cycles": 0,
                "assessment": "stable",
            },
            "supervisor_activity": {"blocked_rate": 0.0, "blocked_reason_top": {}},
            "incident_postmortem": {"incidents": []},
            "trade_summary": {"trade_count": 1, "symbols_traded": ["005930"], "symbol_hold_durations": []},
            "trade_decision_summaries": {"trade_summaries": [{"estimated_realized_pnl": 1.0}]},
            "operator_facing_summary": {"summary_lines": ["good run"]},
            "report_focus_targets": ["theme_accuracy"],
        },
        path=memory_path,
        timestamp="2026-03-10T15:30:00+00:00",
    )
    monkeypatch.setenv("STRATEGY_MEMORY_PATH", str(memory_path))
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterOk)

    logger = _MemoryLogger()
    out = strategist_node(_base_state(logger))

    feedback = out.get("recent_strategy_feedback") or {}
    assert feedback.get("feedback_window_size") == 1
    assert "semiconductor" in (feedback.get("recent_theme_performance") or {})
    strategist_output = out.get("strategist_output") or {}
    assert (strategist_output.get("recent_strategy_feedback") or {}).get("feedback_window_size") == 1

    trace_rows = [r for r in logger.rows if r.get("stage") == "decision_trace" and r.get("event") == "strategic_frame"]
    assert len(trace_rows) == 1
    trace_payload = ((trace_rows[0].get("payload") or {}).get("payload") or {})
    assert trace_payload.get("feedback_window_size") == 1


def test_strategist_recent_feedback_is_advisory_not_hard_override(monkeypatch, tmp_path):
    memory_path = tmp_path / "strategy_memory" / "feedback.jsonl"
    save_strategy_feedback(
        "reporter-2026-03-10",
        {
            "day": "2026-03-10",
            "strategy_frame_summary": {"theme_top": {"defense": 1}, "playbook_top": {"defensive": 1}},
            "strategist_evaluation": {
                "themes_proposed": ["defense"],
                "theme_alignment_status": "aligned",
                "assessment": "aligned",
            },
            "scanner_evaluation": {"selection_status": "stable"},
            "monitor_evaluation": {"monitor_status": "stable"},
            "supervisor_activity": {"blocked_rate": 0.0},
            "incident_postmortem": {"incidents": []},
            "trade_summary": {"trade_count": 1, "symbols_traded": ["069500"], "symbol_hold_durations": []},
            "trade_decision_summaries": {"trade_summaries": [{"estimated_realized_pnl": 0.5}]},
            "operator_facing_summary": {"summary_lines": ["good run"]},
            "report_focus_targets": ["theme_accuracy"],
        },
        path=memory_path,
        timestamp="2026-03-10T15:30:00+00:00",
    )
    monkeypatch.setenv("STRATEGY_MEMORY_PATH", str(memory_path))
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterOk)

    logger = _MemoryLogger()
    out = strategist_node(_base_state(logger))

    strategist_output = out.get("strategist_output") or {}
    assert strategist_output.get("themes") == ["semiconductor", "ai"]
    assert strategist_output.get("playbook") == "breakout"
    feedback = strategist_output.get("recent_strategy_feedback") or {}
    assert feedback.get("feedback_window_size") == 1
    assert "defense" in (feedback.get("recent_theme_performance") or {})


def test_strategist_produces_feedback_field_even_when_memory_empty(monkeypatch, tmp_path):
    memory_path = tmp_path / "strategy_memory" / "feedback.jsonl"
    monkeypatch.setenv("STRATEGY_MEMORY_PATH", str(memory_path))
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "false")

    logger = _MemoryLogger()
    out = strategist_node(_base_state(logger))

    feedback = out.get("recent_strategy_feedback") or {}
    assert feedback.get("feedback_window_size") == 0
    strategist_output = out.get("strategist_output") or {}
    assert (strategist_output.get("recent_strategy_feedback") or {}).get("feedback_window_size") == 0
    assert strategist_output.get("playbook") in ("breakout", "pullback", "reversal", "defensive")


def test_strategist_recent_feedback_can_be_disabled_by_commander_applied_policy(monkeypatch, tmp_path):
    memory_path = tmp_path / "strategy_memory" / "feedback.jsonl"
    save_strategy_feedback(
        "reporter-2026-03-10",
        {
            "day": "2026-03-10",
            "strategy_frame_summary": {"theme_top": {"semiconductor": 1}},
            "strategist_evaluation": {"themes_proposed": ["semiconductor"], "assessment": "aligned"},
            "scanner_evaluation": {"selection_status": "stable"},
            "monitor_evaluation": {"monitor_status": "stable"},
            "supervisor_activity": {"blocked_rate": 0.0},
            "incident_postmortem": {"incidents": []},
            "trade_summary": {"trade_count": 1, "symbols_traded": ["005930"], "symbol_hold_durations": []},
            "trade_decision_summaries": {"trade_summaries": [{"estimated_realized_pnl": 1.0}]},
            "operator_facing_summary": {"summary_lines": ["good run"]},
            "report_focus_targets": ["theme_accuracy"],
        },
        path=memory_path,
        timestamp="2026-03-10T15:30:00+00:00",
    )
    monkeypatch.setenv("STRATEGY_MEMORY_PATH", str(memory_path))
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "false")

    logger = _MemoryLogger()
    state = _base_state(logger)
    state["applied_policy"] = {"strategist": {"memory_feedback": {"enabled": False, "policy_source": "commander_applied_policy"}}}

    out = strategist_node(state)

    feedback = out.get("recent_strategy_feedback") or {}
    assert feedback.get("status") == "disabled"
    assert feedback.get("policy_source") == "commander_applied_policy"
    assert feedback.get("feedback_window_size") == 0


def test_strategist_reporter_feedback_mode_disabled_ignores_packet(monkeypatch):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterOk)

    logger = _MemoryLogger()
    state = _base_state(logger)
    state["applied_policy"] = {
        "strategist": {
            "reporter_feedback_mode": "disabled",
            "reporter_feedback_mode_source": "commander_applied_policy",
        }
    }
    state["strategist_feedback_packet"] = {
        "available": True,
        "status": "ok",
        "confidence": "high",
        "insight_summary": "Monitor-only share is high.",
        "route_analysis": {"route_selected_total": {"monitor_only": 12, "full_cycle": 3}},
        "recommendation": ["Review monitor-only concentration."],
    }

    out = strategist_node(state)

    strategist_output = out.get("strategist_output") or {}
    assert strategist_output.get("playbook") == "breakout"
    assert strategist_output.get("themes") == ["semiconductor", "ai"]
    reporter_feedback = strategist_output.get("reporter_feedback_packet") or {}
    assert reporter_feedback.get("status") == "disabled"
    assert reporter_feedback.get("available") is False
    assert reporter_feedback.get("reporter_feedback_mode") == "disabled"
    assert reporter_feedback.get("reporter_feedback_mode_source") == "commander_applied_policy"
    assert reporter_feedback.get("feedback_gate_reason") == "mode_disabled"


def test_strategist_reporter_feedback_mode_enabled_consumes_advisory_only(monkeypatch):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterOk)

    logger = _MemoryLogger()
    state = _base_state(logger)
    state["applied_policy"] = {
        "strategist": {
            "reporter_feedback_mode": "enabled",
            "reporter_feedback_mode_source": "commander_applied_policy",
        }
    }
    state["strategist_feedback_packet"] = {
        "available": True,
        "status": "ok",
        "feedback_mode": "deterministic",
        "confidence": "medium",
        "insight_summary": "Reclaim blockers are elevated while monitor-only remains dominant.",
        "route_analysis": {
            "route_source": "canonical_commander_preferred",
            "route_selected_total": {"monitor_only": 12, "cached_strategist": 5, "full_cycle": 3},
            "monitor_only_ratio": 0.6,
            "cached_strategist_ratio": 0.25,
            "full_cycle_ratio": 0.15,
        },
        "blocker_analysis": [
            {"blocker": "below_vwap_reclaim_not_ready", "count": 6, "ratio": 0.3},
            {"blocker": "pullback_ok", "count": 5, "ratio": 0.25},
        ],
        "recommendation": [
            "Review reclaim readiness evidence.",
            "Compare cached strategist reuse against fresh full-cycle opportunities.",
        ],
    }

    out = strategist_node(state)

    strategist_output = out.get("strategist_output") or {}
    assert strategist_output.get("playbook") == "breakout"
    assert strategist_output.get("themes") == ["semiconductor", "ai"]
    reporter_feedback = strategist_output.get("reporter_feedback_packet") or {}
    assert reporter_feedback.get("available") is True
    assert reporter_feedback.get("status") == "ok"
    assert reporter_feedback.get("reporter_feedback_mode") == "enabled"
    assert reporter_feedback.get("reporter_feedback_mode_source") == "commander_applied_policy"
    assert reporter_feedback.get("consumed") is True
    assert reporter_feedback.get("feedback_gate_reason") == "mode_enabled"
    assert reporter_feedback.get("insight_summary") == "Reclaim blockers are elevated while monitor-only remains dominant."

    frame = out.get("strategist_decision_frame") or {}
    assert (frame.get("reporter_feedback_packet") or {}).get("available") is True
    assert (frame.get("reporter_feedback_packet") or {}).get("confidence") == "medium"

    trace_rows = [r for r in logger.rows if r.get("stage") == "decision_trace" and r.get("event") == "strategic_frame"]
    assert len(trace_rows) == 1
    trace_payload = ((trace_rows[0].get("payload") or {}).get("payload") or {})
    assert trace_payload.get("reporter_feedback_available") is True
    assert trace_payload.get("reporter_feedback_status") == "ok"
    assert trace_payload.get("reporter_feedback_mode") == "enabled"
    assert trace_payload.get("reporter_feedback_mode_source") == "commander_applied_policy"
    assert trace_payload.get("reporter_feedback_gate_reason") == "mode_enabled"


def test_strategist_reporter_feedback_falls_back_to_metrics_when_state_packet_missing(monkeypatch, tmp_path):
    reports_root = tmp_path / "reports"
    day = "2026-03-20"
    metrics_dir = reports_root / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    (metrics_dir / f"metrics_{day}.json").write_text(
        json.dumps(
            {
                "day": day,
                "route_selected_total": {"monitor_only": 12, "cached_strategist": 5, "full_cycle": 3},
                "strategist_fallback_total": 5,
                "route_source": "canonical_commander_preferred",
                "route_source_run_count": 20,
                "route_source_missing_count": 0,
                "route_source_breakdown": {"canonical_commander": 20},
                "dominant_blocker_total": {"rebound_ok": 6, "reclaim_gate_ok": 4},
                "data_freshness": {
                    "generated_at": "2026-03-20T09:10:00+00:00",
                    "source_run_count": 20,
                    "latest_run_id": "report-bundle",
                    "latest_run_ts": "2026-03-20T09:09:00+00:00",
                    "freshness_status": "fresh",
                    "stale": False,
                    "stale_reason": "aligned_with_source_window",
                    "source_window_summary": "runs=20",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "false")
    logger = _MemoryLogger()
    state = _base_state(logger)
    state["reports_root"] = str(reports_root)
    state["day"] = day

    out = strategist_node(state)

    reporter_feedback = out.get("reporter_feedback_packet") or {}
    assert reporter_feedback.get("available") is True
    assert reporter_feedback.get("status") == "ok"
    assert reporter_feedback.get("consumed") is True
    assert reporter_feedback.get("feedback_gate_reason") == "auto_accepted"
    assert (reporter_feedback.get("route_analysis") or {}).get("monitor_only_ratio") == 0.6


def test_strategist_reporter_feedback_falls_back_to_reporter_analysis_when_metrics_missing(monkeypatch, tmp_path):
    reports_root = tmp_path / "reports"
    day = "2026-03-20"
    reporter_dir = reports_root / "dev" / "analysis" / "reporter_analysis"
    reporter_dir.mkdir(parents=True, exist_ok=True)
    (reporter_dir / f"reporter_analysis_{day}.json").write_text(
        json.dumps(
            {
                "day": day,
                "generated_at": "2026-03-20T09:11:00+00:00",
                "monitor_evaluation": {
                    "monitor_reason_top": {
                        "too_extended_from_vwap": 8,
                        "volume_insufficient": 4,
                    }
                },
                "supervisor_activity": {
                    "blocked_reason_top": {
                        "noop_intent_skipped": 11
                    }
                },
                "operator_facing_summary": {
                    "recommended_actions": [
                        "Reduce extended-entry tolerance before broadening selection."
                    ]
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "false")
    logger = _MemoryLogger()
    state = _base_state(logger)
    state["reports_root"] = str(reports_root)
    state["day"] = day

    out = strategist_node(state)

    reporter_feedback = out.get("reporter_feedback_packet") or {}
    assert reporter_feedback.get("available") is True
    assert reporter_feedback.get("status") == "ok"
    assert reporter_feedback.get("consumed") is True
    assert reporter_feedback.get("feedback_gate_reason") == "auto_accepted"
    assert reporter_feedback.get("source_available") is True
    assert reporter_feedback.get("source_reports", {}).get("reporter_analysis") is True
    assert (reporter_feedback.get("blocker_analysis") or [])[0]["blocker"] == "noop_intent_skipped"


def test_strategist_reporter_feedback_falls_back_to_same_day_trade_reports_when_reports_exist(monkeypatch, tmp_path):
    reports_root = tmp_path / "reports"
    day = "2026-04-23"
    trade_dir = reports_root / "trades" / day / "TRD_20260423_005930_01" / "reports"
    trade_dir.mkdir(parents=True, exist_ok=True)
    (trade_dir / "ai_trade_report.json").write_text(
        json.dumps(
            {
                "trade_id": "TRD_20260423_005930_01",
                "symbol": "005930",
                "truth_surface": {
                    "status": {
                        "symbol": "005930",
                        "status": "closed",
                        "exit_reason": "SELL was triggered because peak_drawdown.",
                    },
                    "price": {
                        "broker_buy_price": 224500.0,
                        "broker_fill_price": 226000.0,
                    },
                    "pnl": {
                        "value": -522.0,
                        "pct": -0.0023,
                        "broker_fee": 1570,
                        "broker_tax": 452,
                    },
                    "availability": {
                        "broker_fill_present": True,
                        "broker_pnl_present": True,
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "false")
    logger = _MemoryLogger()
    state = _base_state(logger)
    state["reports_root"] = str(reports_root)
    state["day"] = day

    out = strategist_node(state)

    reporter_feedback = out.get("reporter_feedback_packet") or {}
    assert reporter_feedback.get("available") is True
    assert reporter_feedback.get("status") == "ok"
    assert reporter_feedback.get("consumed") is True
    assert reporter_feedback.get("feedback_gate_reason") == "auto_accepted"
    assert reporter_feedback.get("source_available") is True
    assert reporter_feedback.get("source_reports", {}).get("trade_reports") is True
    assert (reporter_feedback.get("trade_report_analysis") or {}).get("closed_trade_count") == 1


def test_strategist_reporter_feedback_mode_auto_consumes_fresh_relevant_packet(monkeypatch):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterOk)

    logger = _MemoryLogger()
    state = _base_state(logger)
    state["applied_policy"] = {
        "strategist": {
            "reporter_feedback_mode": "auto",
            "reporter_feedback_mode_source": "commander_applied_policy",
        }
    }
    state["strategist_feedback_packet"] = {
        "available": True,
        "status": "ok",
        "feedback_mode": "deterministic",
        "confidence": "high",
        "insight_summary": "Fresh route context is available for advisory review.",
        "route_analysis": {
            "route_source": "canonical_commander_preferred",
            "route_selected_total": {"monitor_only": 8, "full_cycle": 4},
            "monitor_only_ratio": 0.6667,
            "full_cycle_ratio": 0.3333,
        },
        "recommendation": ["Review monitor-only concentration before broadening playbook assumptions."],
        "data_freshness": {"freshness_status": "fresh", "stale": False},
    }

    out = strategist_node(state)

    strategist_output = out.get("strategist_output") or {}
    assert strategist_output.get("playbook") == "breakout"
    assert strategist_output.get("themes") == ["semiconductor", "ai"]
    reporter_feedback = strategist_output.get("reporter_feedback_packet") or {}
    assert reporter_feedback.get("available") is True
    assert reporter_feedback.get("status") == "ok"
    assert reporter_feedback.get("reporter_feedback_mode") == "auto"
    assert reporter_feedback.get("reporter_feedback_mode_source") == "commander_applied_policy"
    assert reporter_feedback.get("consumed") is True
    assert reporter_feedback.get("feedback_gate_reason") == "auto_accepted"
    trace_rows = [r for r in logger.rows if r.get("stage") == "decision_trace" and r.get("event") == "strategic_frame"]
    assert len(trace_rows) == 1
    trace_payload = ((trace_rows[0].get("payload") or {}).get("payload") or {})
    assert trace_payload.get("reporter_feedback_consumed") is True
    assert trace_payload.get("reporter_feedback_confidence") == "high"


def test_strategist_reporter_feedback_mode_auto_ignores_stale_packet(monkeypatch):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterOk)

    logger = _MemoryLogger()
    state = _base_state(logger)
    state["applied_policy"] = {
        "strategist": {
            "reporter_feedback_mode": "auto",
            "reporter_feedback_mode_source": "commander_applied_policy",
        }
    }
    state["strategist_feedback_packet"] = {
        "available": True,
        "status": "ok",
        "feedback_mode": "deterministic",
        "confidence": "high",
        "insight_summary": "This packet is stale and should be ignored.",
        "route_analysis": {"route_selected_total": {"monitor_only": 12}},
        "recommendation": ["Ignore stale packet."],
        "data_freshness": {"freshness_status": "stale", "stale": True, "stale_reason": "source_window_behind"},
    }

    out = strategist_node(state)

    strategist_output = out.get("strategist_output") or {}
    assert strategist_output.get("playbook") == "breakout"
    assert strategist_output.get("themes") == ["semiconductor", "ai"]
    reporter_feedback = strategist_output.get("reporter_feedback_packet") or {}
    assert reporter_feedback.get("available") is False
    assert reporter_feedback.get("status") == "auto_ignored"
    assert reporter_feedback.get("reporter_feedback_mode") == "auto"
    assert reporter_feedback.get("reporter_feedback_mode_source") == "commander_applied_policy"
    assert reporter_feedback.get("consumed") is False
    assert reporter_feedback.get("feedback_gate_reason") == "stale"


def test_strategist_reporter_feedback_mode_auto_ignores_missing_packet(monkeypatch, tmp_path):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterOk)

    logger = _MemoryLogger()
    state = _base_state(logger)
    state["applied_policy"] = {
        "strategist": {
            "reporter_feedback_mode": "auto",
            "reporter_feedback_mode_source": "commander_applied_policy",
        }
    }
    state["reports_root"] = str(tmp_path / "reports")
    state["day"] = "2026-04-30"

    out = strategist_node(state)

    strategist_output = out.get("strategist_output") or {}
    assert strategist_output.get("playbook") == "breakout"
    assert strategist_output.get("themes") == ["semiconductor", "ai"]
    reporter_feedback = strategist_output.get("reporter_feedback_packet") or {}
    assert reporter_feedback.get("available") is False
    assert reporter_feedback.get("status") == "auto_ignored"
    assert reporter_feedback.get("reporter_feedback_mode") == "auto"
    assert reporter_feedback.get("reporter_feedback_mode_source") == "commander_applied_policy"
    assert reporter_feedback.get("feedback_gate_reason") == "source_unavailable"


def test_strategist_prefers_commander_canonical_mode_over_state_fallback(monkeypatch):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterOk)

    logger = _MemoryLogger()
    state = _base_state(logger)
    state["reporter_feedback_mode"] = "enabled"
    state["applied_policy"] = {
        "reporter_feedback_mode": "enabled",
        "strategist": {
            "reporter_feedback_mode": "disabled",
            "reporter_feedback_mode_source": "commander_applied_policy",
        },
    }
    state["strategist_feedback_packet"] = {
        "available": True,
        "status": "ok",
        "confidence": "high",
        "insight_summary": "Canonical commander mode should win.",
    }

    out = strategist_node(state)

    strategist_output = out.get("strategist_output") or {}
    assert strategist_output.get("playbook") == "breakout"
    assert strategist_output.get("themes") == ["semiconductor", "ai"]
    reporter_feedback = strategist_output.get("reporter_feedback_packet") or {}
    assert reporter_feedback.get("status") == "disabled"
    assert reporter_feedback.get("reporter_feedback_mode") == "disabled"
    assert reporter_feedback.get("reporter_feedback_mode_source") == "commander_applied_policy"
    assert reporter_feedback.get("feedback_gate_reason") == "mode_disabled"


def test_strategist_reporter_feedback_mode_state_fallback_remains_supported(monkeypatch):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterOk)

    logger = _MemoryLogger()
    state = _base_state(logger)
    state["reporter_feedback_mode"] = "enabled"
    state["strategist_feedback_packet"] = {
        "available": True,
        "status": "ok",
        "confidence": "medium",
        "insight_summary": "State fallback remains supported for compatibility.",
        "route_analysis": {"route_selected_total": {"monitor_only": 4, "full_cycle": 2}},
    }

    out = strategist_node(state)

    strategist_output = out.get("strategist_output") or {}
    assert strategist_output.get("playbook") == "breakout"
    assert strategist_output.get("themes") == ["semiconductor", "ai"]
    reporter_feedback = strategist_output.get("reporter_feedback_packet") or {}
    assert reporter_feedback.get("available") is True
    assert reporter_feedback.get("reporter_feedback_mode") == "enabled"
    assert reporter_feedback.get("reporter_feedback_mode_source") == "state_fallback"
    assert reporter_feedback.get("consumed") is True


def test_build_compact_strategist_llm_payload_trims_memory_and_news() -> None:
    payload = {
        "global_sentiment_signal": {
            "score": -0.173829,
            "status": "ok",
            "source": "yfinance",
            "index_moves": {"sp500_pct": -1.5232, "nasdaq_pct": -1.7811, "dow_pct": -1.5511},
            "macro_moves": {"vix_pct": 3.4455, "vix_level": 26.556, "vix_level_pressure": 0.3277, "dxy_pct": 0.4112, "tnx_delta": 0.00652},
            "fear_index": {"level": 26.556, "change_pct": 3.4455, "level_pressure": 0.3277},
        },
        "news_context": {"signal_total": 13, "avg_score": 0.09234, "headline_count": 65, "candidate_signal_total": 5, "market_signal_total": 8},
        "market_context_inputs": {"index_trend": 0.0, "realized_volatility": 0.012345, "market_breadth": 0.0, "macro_risk": 0.12555},
        "recent_strategy_feedback": {
            "feedback_window_size": 12,
            "top_recent_strengths": ["a", "b", "c", "d"],
            "top_recent_weaknesses": ["w1", "w2", "w3", "w4", "w5"],
            "recent_reporter_summary": ["s1", "s2", "s3"],
            "suggested_report_focus": ["f1", "f2", "f3", "f4", "f5"],
            "recent_theme_performance": {"semiconductor": {"appearance_count": 4}, "defense": {"appearance_count": 6}, "ai": {"appearance_count": 2}, "energy": {"appearance_count": 1}},
            "recent_playbook_performance": {"pullback": {"appearance_count": 9}, "defensive": {"appearance_count": 3}, "breakout": {"appearance_count": 1}, "reversal": {"appearance_count": 2}},
            "advisory_only": True,
        },
        "reporter_feedback_packet": {
            "available": True,
            "status": "ok",
            "feedback_mode": "deterministic",
            "confidence": "medium",
            "insight_summary": "Monitor-only share is elevated and reclaim blockers are common.",
            "route_analysis": {
                "route_source": "canonical_commander_preferred",
                "route_selected_total": {"monitor_only": 12, "cached_strategist": 5, "full_cycle": 3},
                "monitor_only_ratio": 0.6,
                "cached_strategist_ratio": 0.25,
                "full_cycle_ratio": 0.15,
            },
            "blocker_analysis": [
                {"blocker": "below_vwap_reclaim_not_ready", "count": 6, "ratio": 0.3},
                {"blocker": "pullback_ok", "count": 5, "ratio": 0.25},
            ],
            "dominant_patterns": [
                {"name": "monitor_only_ratio", "value": 0.6, "detail": "monitor_only 12/20"},
                {"name": "reclaim_blocked_ratio", "value": 0.3, "detail": "reclaim blockers 6/20"},
            ],
            "recommendation": [
                "Review reclaim readiness evidence.",
                "Compare cached strategist reuse against fresh full-cycle opportunities.",
            ],
        },
        "macro_stress_overlay_hint": {"active": True, "stress_flags": ["elevated_vix", "dollar_strength", "yield_rise", "extra"], "reason": "macro stress"},
        "market_news_sample": {
            "코스피": {"count": 5, "sample": [{"title": "a" * 140}, {"title": "b"}]},
            "미국 증시": {"count": 5, "sample": [{"title": "c"}]},
            "달러": {"count": 5, "sample": [{"title": "d"}]},
            "방산": {"count": 5, "sample": [{"title": "e"}]},
            "금": {"count": 5, "sample": [{"title": "f"}]},
        },
        "candidate_news_sample": {
            "005930": {"count": 5, "sample": [{"title": "g" * 140}, {"title": "h"}]},
            "000660": {"count": 5, "sample": [{"title": "i"}]},
            "069500": {"count": 5, "sample": [{"title": "j"}]},
            "122630": {"count": 5, "sample": [{"title": "k"}]},
            "032820": {"count": 5, "sample": [{"title": "l"}]},
        },
        "candidate_symbols_hint": ["1", "2", "3", "4", "5", "6"],
        "key_events_hint": ["e1", "e2", "e3", "e4", "e5"],
        "themes_hint": ["t1", "t2", "t3", "t4", "t5"],
        "news_query_targets": ["n1", "n2", "n3", "n4", "n5", "n6", "n7", "n8", "n9"],
        "commander_refresh_context": {
            "requested": True,
            "reason": "repeated_hold_monitor_only",
            "refresh_scope": "open_position_monitor_refresh",
            "selected_symbol": "000660",
            "hold_repeat_count_max": 3,
            "selected_hold_repeat_count": 3,
            "monitor_reason": "too_extended_from_vwap",
            "active_exit_axis": "peak_drawdown",
            "refresh_summary": "Repeated hold refresh for 000660 after 3 consecutive hold cycles. Current blocking axis is reclaim_readiness.",
            "entry_state": {"current_blocking_axis": "reclaim_readiness", "entry_blockers": ["below_vwap_reclaim_not_ready"]},
            "prior_monitor_entry_policy_summary": {"volume_ratio_min": 0.68},
            "current_monitor_entry_policy_summary": {"volume_ratio_min": 0.68},
            "requires_policy_delta": True,
            "selected_symbol_memory": {
                "symbol": "000660",
                "trade_count": 9,
                "win_rate": 0.4444,
                "dominant_playbook": "pullback",
                "dominant_monitor_blocker": "below_vwap_reclaim_not_ready",
            },
        },
        "memory_packets": {
            "daily_strategy_memory": {
                "status": "ok",
                "best_playbooks": ["defensive", "pullback"],
                "worst_playbooks": ["breakout"],
            },
            "weekly_strategy_memory": {"status": "unavailable"},
            "monthly_strategy_memory": {"status": "unavailable"},
            "symbol_memory_packet": {
                "status": "ok",
                "symbol": "000660",
                "trade_count": 9,
                "override_eligible": True,
            },
        },
        "commander_memory_policy": {
            "application_mode": "surface_only",
            "active_layers": ["daily", "symbol"],
            "priority_order": ["daily", "symbol", "weekly", "monthly"],
            "symbol_memory_override_enabled": True,
            "scanner_bias_enabled": True,
            "monitor_bias_enabled": True,
        },
        "monitor_memory_bias": {
            "enabled": True,
            "active_layers": ["daily", "symbol"],
            "entry_policy_delta": {"volume_ratio_min": 0.03},
            "risk_posture": "defensive",
        },
    }

    compact = _build_compact_strategist_llm_payload(payload)

    assert compact["global_sentiment_signal"]["score"] == -0.1738
    assert compact["token_budget_policy"]["stage_specific_context"] is True
    assert "theme_strength_packet" not in compact
    assert "theme_strength_packet_summary" in compact
    assert "top_recent_strengths" not in compact["recent_strategy_feedback"]
    assert len(compact["recent_strategy_feedback"]["top_recent_weaknesses"]) == 2
    assert "suggested_report_focus" not in compact["recent_strategy_feedback"]
    assert "recent_theme_performance" not in compact["recent_strategy_feedback"]
    assert compact["reporter_feedback_packet"]["available"] is True
    assert "route_analysis" not in compact["reporter_feedback_packet"]
    assert len(compact["reporter_feedback_packet"]["blocker_analysis"]) == 2
    assert len(compact["reporter_feedback_packet"]["recommendation"]) == 2
    assert compact["market_news_sample"] == {}
    assert compact["candidate_news_sample"] == {}
    assert len(compact["candidate_symbols_hint"]) == 5
    assert len(compact["key_events_hint"]) == 4
    assert len(compact["themes_hint"]) == 4
    assert len(compact["news_query_targets"]) == 8
    assert compact["commander_refresh_context"]["requested"] is True
    assert compact["commander_refresh_context"]["selected_symbol"] == "000660"
    assert compact["commander_refresh_context"]["requires_policy_delta"] is True
    assert compact["commander_refresh_context"]["selected_symbol_memory"]["symbol"] == "000660"
    assert "dominant_playbook" not in compact["commander_refresh_context"]["selected_symbol_memory"]
    assert compact["strategy_refresh_trace_input"]["post_scanner_refresh"]["selected_symbol"] == "000660"
    assert compact["strategy_refresh_trace_input"]["final_application"]["requires_policy_delta"] is True
    assert compact["memory_packets"]["daily_strategy_memory"]["status"] == "ok"
    assert compact["memory_packets"]["symbol_memory_packet"]["symbol"] == "000660"
    assert "weekly_strategy_memory" not in compact["memory_packets"]
    assert "monthly_strategy_memory" not in compact["memory_packets"]
    assert compact["commander_memory_policy"]["application_mode"] == "surface_only"
    assert compact["commander_memory_policy"]["active_layers"] == ["daily", "symbol"]
    assert compact["monitor_memory_bias"]["enabled"] is True
    assert compact["monitor_memory_bias"]["risk_posture"] == "defensive"


def test_build_strategist_llm_messages_enforces_read_model_facts_and_policy_adjustment() -> None:
    messages = _build_strategist_llm_messages({"read_model_facts": {}, "commander_refresh_context": {}})

    system = str(messages[0]["content"])
    user = str(messages[1]["content"])

    assert "You MUST use the provided deterministic memory packets as primary constraints" in system
    assert "You MUST convert those inputs into explicit strategy adjustment directives." in system
    assert "strategy_adjustment_directives" in user
    assert "If repeated failure is concentrated in one axis" in user
    assert '"refresh_action"' in user
    assert "strategy_refresh_trace" in user
    assert "1st/base frame" in system


def test_build_strategist_llm_messages_disables_memory_usage_when_policy_disabled() -> None:
    messages = _build_strategist_llm_messages(
        {
            "read_model_facts": {},
            "commander_refresh_context": {},
            "commander_memory_policy": {"application_mode": "disabled", "disabled": True},
        }
    )

    system = str(messages[0]["content"])
    user = str(messages[1]["content"])

    assert "Memory packets are temporarily disabled by Commander policy" in system
    assert "Do not use memory fields to adjust playbook" in system
    assert "Memory usage is temporarily disabled" in user
    assert "The memory packets are not optional background" not in user


def test_compact_strategist_llm_payload_limits_read_model_and_operator_summary_bulk() -> None:
    payload = {
        "read_model_facts": {
            "recent_trades": [
                {
                    "trade_id": f"T{i}",
                    "symbol": "005930",
                    "entry_reason": "breakout_above_recent_high_with_vwap_structure_confirmation",
                    "exit_reason": "stop_loss",
                    "pnl_pct": -0.01,
                    "raw_story_blob": "x" * 5000,
                }
                for i in range(8)
            ],
            "symbol_patterns": {
                "005930": {
                    "symbol": "005930",
                    "trade_count": 12,
                    "win_rate": 0.25,
                    "dominant_monitor_blocker": "below_vwap_reclaim_not_ready",
                    "repeated_failure_pattern": [
                        {"type": "blocker", "value": "below_vwap_reclaim_not_ready", "count": 7, "raw": "y" * 1000}
                    ],
                    "trade_history": [{"raw": "z" * 5000}],
                }
            },
        },
        "memory_packets": {
            "daily_strategy_memory": {
                "status": "ok",
                "operator_summary": {
                    "available": True,
                    "metrics": {"trade_count": 5, "win_rate": 0.2},
                    "operator_view": {
                        "conclusion": "review " * 100,
                        "review_points": ["entry", "exit", "cost", "risk", "extra"],
                    },
                    "raw_rows": [{"raw": "a" * 5000}],
                },
            },
            "weekly_strategy_memory": {"status": "unavailable"},
            "monthly_strategy_memory": {"status": "unavailable"},
            "symbol_memory_packet": {"status": "empty", "symbol": "005930"},
        },
    }

    compact = _build_compact_strategist_llm_payload(payload)
    encoded = json.dumps(compact, ensure_ascii=False)

    assert compact["read_model_facts"]["recent_trade_count"] == 8
    assert len(compact["read_model_facts"]["recent_trades"]) == 3
    assert "raw_story_blob" not in encoded
    assert "trade_history" not in encoded
    assert "raw_rows" not in encoded
    assert compact["memory_packets"]["daily_strategy_memory"]["operator_summary"]["metrics"]["trade_count"] == 5
    assert len(compact["memory_packets"]["daily_strategy_memory"]["operator_summary"]["operator_view"]["review_points"]) == 4
    assert len(encoded) < 8000


def test_stage1_compact_payload_excludes_symbol_memory_until_selected_refresh() -> None:
    payload = {
        "read_model_facts": {
            "symbol_patterns": {
                "005930": {
                    "symbol": "005930",
                    "trade_count": 8,
                    "dominant_monitor_blocker": "below_vwap_reclaim_not_ready",
                }
            }
        },
        "memory_packets": {
            "daily_strategy_memory": {"status": "ok"},
            "weekly_strategy_memory": {"status": "ok"},
            "monthly_strategy_memory": {"status": "ok"},
            "symbol_memory_packet": {"status": "ok", "symbol": "005930", "trade_count": 8},
        },
        "commander_refresh_context": {"requested": False},
    }

    compact = _build_compact_strategist_llm_payload(payload)

    assert compact["resolved_call_kind"] == "market_strategy_frame"
    assert compact["read_model_facts"]["symbol_patterns"] == {}
    assert compact["read_model_facts"]["symbol_pattern_count"] == 0
    assert compact["memory_packets"]["symbol_memory_packet"]["status"] == "excluded"
    assert compact["memory_boundary"]["symbol_memory_visible_to_llm"] is False


def test_compact_payload_resolves_stage3_and_stage4_call_kinds() -> None:
    stage3 = _build_compact_strategist_llm_payload(
        {
            "commander_refresh_context": {
                "requested": True,
                "reason": "repeated_hold_monitor_only",
                "refresh_scope": "open_position_monitor_refresh",
                "selected_symbol": "005930",
            }
        }
    )
    stage4 = _build_compact_strategist_llm_payload(
        {
            "commander_refresh_context": {
                "requested": True,
                "reason": "session_closeout_carry_review",
                "refresh_scope": "session_closeout_carry_review",
                "selected_symbol": "005930",
            }
        }
    )
    preopen = _build_compact_strategist_llm_payload(
        {
            "commander_refresh_context": {
                "requested": True,
                "reason": "preopen_carry_risk_review",
                "refresh_scope": "preopen_open_position_review",
                "selected_symbol": "005930",
            }
        }
    )

    assert stage3["resolved_call_kind"] == "stale_intraday_hold_review"
    assert stage4["resolved_call_kind"] == "end_of_day_carry_review"
    assert preopen["resolved_call_kind"] == "stale_intraday_hold_review"


def test_stage_specific_llm_messages_match_4stage_contracts() -> None:
    stage2_messages = _build_strategist_llm_messages(
        {
            "commander_refresh_context": {
                "requested": True,
                "reason": "selected_symbol_tactical_refresh",
                "refresh_scope": "selected_symbol_tactical_refresh",
                "selected_symbol": "005930",
            }
        }
    )
    stage2_user = stage2_messages[1]["content"]
    assert "selected_symbol_decision" in stage2_user
    assert "runner_up_order" in stage2_user
    assert "commander_actionability" in stage2_user
    assert "choose exactly ONE playbook" not in stage2_user

    stage3_messages = _build_strategist_llm_messages(
        {
            "commander_refresh_context": {
                "requested": True,
                "reason": "repeated_hold_monitor_only",
                "refresh_scope": "open_position_monitor_refresh",
                "selected_symbol": "005930",
            }
        }
    )
    stage3_system = stage3_messages[0]["content"]
    stage3_user = stage3_messages[1]["content"]
    assert "unrelated candidate themes" in stage3_system
    assert "hold_review_decision" in stage3_user
    assert "monitor_adjustment" in stage3_user
    assert "held symbol under review" in stage3_user

    stage4_user = _build_strategist_llm_messages(
        {
            "commander_refresh_context": {
                "requested": True,
                "reason": "session_closeout_carry_review",
                "refresh_scope": "session_closeout_carry_review",
                "selected_symbol": "005930",
            }
        }
    )[1]["content"]
    assert "carry_review" in stage4_user
    assert "portfolio_level_decision" in stage4_user


def test_strategist_llm_payload_includes_commander_refresh_context(monkeypatch):
    captured = {}

    def fake_run_strategist_frame_llm(*, state, policy, payload):
        captured["payload"] = dict(payload or {})
        return ({}, {"status": "disabled", "attempts": 0, "repair_used": False, "reason": "test_capture"})

    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setattr("graphs.nodes.strategist_node._run_strategist_frame_llm", fake_run_strategist_frame_llm)

    logger = _MemoryLogger()
    state = _base_state(logger)
    state["commander_decision"] = {
        "market_regime": "neutral",
        "session_bias": "position_management",
        "risk_mode": "balanced",
        "command_intent": "REFRESH_STRATEGY_FRAME",
        "strategist_invocation": "RUN_REFRESH",
        "llm_policy": "allow_context_refresh",
        "strategist_refresh_requested": True,
        "strategist_refresh_reason": "repeated_hold_monitor_only",
        "strategist_refresh_context": {
            "prior_monitor_entry_policy_summary": {"volume_ratio_min": 0.68},
            "current_monitor_entry_policy_summary": {"volume_ratio_min": 0.68},
        },
        "open_position_refresh_context": {
            "refresh_scope": "open_position_monitor_refresh",
            "selected_symbol": "000660",
            "hold_repeat_count_max": 3,
            "selected_hold_repeat_count": 3,
            "monitor_reason": "too_extended_from_vwap",
            "active_exit_axis": "peak_drawdown",
            "refresh_summary": "Repeated hold refresh for 000660 after 3 consecutive hold cycles.",
            "entry_state": {
                "current_blocking_axis": "reclaim_readiness",
                "entry_blockers": ["below_vwap_reclaim_not_ready"],
            },
        },
    }
    state["reports_root"] = "reports"

    def fake_build_symbol_read_model(trades_root, symbol):
        assert symbol == "000660"
        return {
            "symbol": "000660",
            "trade_count": 11,
            "closed_trade_count": 9,
            "win_rate": 0.5555,
            "avg_pnl_pct": 0.0123,
            "avg_hold_duration_sec": 420.0,
            "dominant_playbook": "pullback",
            "dominant_monitor_blocker": "below_vwap_reclaim_not_ready",
            "dominant_exit_reason": "peak_drawdown",
            "repeated_failure_pattern": [
                {"type": "blocker", "value": "below_vwap_reclaim_not_ready", "count": 3},
            ],
            "recent_success_pattern": [
                {"playbook": "pullback", "entry_reason": "pullback_ok", "exit_reason": "take_profit", "count": 2},
            ],
            "data_quality": {"data_source": "symbol_memory", "unknown_fields_ratio": 0.0},
        }

    monkeypatch.setattr("graphs.nodes.strategist_node.build_symbol_read_model", fake_build_symbol_read_model)

    strategist_node(state)

    llm_payload = dict(captured.get("payload") or {})
    commander_refresh_context = dict(llm_payload.get("commander_refresh_context") or {})
    assert commander_refresh_context["requested"] is True
    assert commander_refresh_context["reason"] == "repeated_hold_monitor_only"
    assert commander_refresh_context["selected_symbol"] == "000660"
    assert commander_refresh_context["monitor_reason"] == "too_extended_from_vwap"
    assert commander_refresh_context["requires_policy_delta"] is True
    assert commander_refresh_context["selected_symbol_memory"]["symbol"] == "000660"
    assert commander_refresh_context["selected_symbol_memory"]["dominant_playbook"] == "pullback"
    assert commander_refresh_context["selected_symbol_memory"]["dominant_monitor_blocker"] == "below_vwap_reclaim_not_ready"


def test_strategist_llm_payload_uses_post_scanner_refresh_symbol_from_strategy_context(monkeypatch):
    captured = {}

    def fake_run_strategist_frame_llm(*, state, policy, payload):
        captured["payload"] = dict(payload or {})
        return ({}, {"status": "disabled", "attempts": 0, "repair_used": False, "reason": "test_capture"})

    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setattr("graphs.nodes.strategist_node._run_strategist_frame_llm", fake_run_strategist_frame_llm)

    logger = _MemoryLogger()
    state = _base_state(logger)
    state["candidate_symbols"] = ["078890", "005930"]
    state["commander_decision"] = {
        "market_regime": "neutral",
        "session_bias": "context_reuse",
        "risk_mode": "balanced",
        "command_intent": "REFRESH_STRATEGY_FRAME",
        "strategist_invocation": "RUN_REFRESH",
        "llm_policy": "allow_context_refresh",
        "strategist_refresh_requested": True,
        "strategist_refresh_reason": "selected_symbol_outside_cached_frame",
        "strategist_refresh_context": {
            "selected_symbol": "078890",
            "selected_rank": 2,
            "selected_score": 0.9701,
            "scanner_primary_candidate": {"rank": 2, "symbol": "078890", "score": 0.9701},
            "actual_selected_candidate": {"rank": 2, "symbol": "078890", "score": 0.9701},
            "scanner_rank1_candidate": {"rank": 1, "symbol": "005930", "score": 0.9842},
            "scanner_runner_ups": [
                {"rank": 1, "symbol": "005930", "score": 0.9842},
                {"rank": 3, "symbol": "000660", "score": 0.9123},
            ],
            "scanner_top_candidates": [
                {"rank": 1, "symbol": "005930", "score": 0.9842},
                {"rank": 2, "symbol": "078890", "score": 0.9701},
                {"rank": 3, "symbol": "000660", "score": 0.9123},
            ],
            "selected_symbol_was_rank1": False,
            "stage2_context_quality": "complete",
            "selected_symbol_in_cached_frame": False,
            "cached_candidate_hints": ["005930", "000660"],
            "prior_monitor_entry_policy_summary": {"volume_ratio_min": 0.68},
            "current_monitor_entry_policy_summary": {"volume_ratio_min": 1.2},
        },
        "open_position_refresh_context": {},
    }
    state["reports_root"] = "reports"

    def fake_build_symbol_read_model(trades_root, symbol, persisted_only=False):
        assert symbol == "078890"
        return {
            "symbol": "078890",
            "trade_count": 2,
            "closed_trade_count": 1,
            "win_rate": 0.0,
            "avg_pnl_pct": -0.004,
            "dominant_playbook": "pullback",
            "dominant_monitor_blocker": "below_vwap_reclaim_not_ready",
            "data_quality": {"data_source": "symbol_memory", "unknown_fields_ratio": 0.0},
        }

    monkeypatch.setattr("graphs.nodes.strategist_node.build_symbol_read_model", fake_build_symbol_read_model)

    out = strategist_node(state)

    llm_payload = dict(captured.get("payload") or {})
    commander_refresh_context = dict(llm_payload.get("commander_refresh_context") or {})
    assert commander_refresh_context["requested"] is True
    assert commander_refresh_context["reason"] == "selected_symbol_outside_cached_frame"
    assert commander_refresh_context["selected_symbol"] == "078890"
    assert commander_refresh_context["selected_rank"] == 2
    assert commander_refresh_context["actual_selected_candidate"]["symbol"] == "078890"
    assert commander_refresh_context["scanner_rank1_candidate"]["symbol"] == "005930"
    assert commander_refresh_context["selected_symbol_was_rank1"] is False
    assert commander_refresh_context["stage2_context_quality"] == "complete"
    assert commander_refresh_context["selected_symbol_memory"]["symbol"] == "078890"
    compact_payload = _build_compact_strategist_llm_payload(llm_payload)
    assert compact_payload["strategy_refresh_trace_input"]["post_scanner_refresh"]["selected_symbol"] == "078890"
    assert compact_payload["strategy_refresh_trace_input"]["post_scanner_refresh"]["scanner_rank1_symbol"] == "005930"
    assert compact_payload["strategy_refresh_trace_input"]["post_scanner_refresh"]["actual_selected_rank"] == 2
    strategic_answers = (out.get("strategist_output") or {}).get("strategic_answers") or {}
    assert strategic_answers["q15_commander_refresh_context"]["selected_symbol"] == "078890"
    assert strategic_answers["q15_commander_refresh_context"]["scanner_rank1_candidate"]["symbol"] == "005930"


def test_stage2_selected_symbol_contract_is_preserved_and_mapped_to_watch_policy(monkeypatch):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.delenv("COMMANDER_MEMORY_USAGE_DISABLED", raising=False)
    monkeypatch.delenv("STRATEGIST_MEMORY_USAGE_DISABLED", raising=False)
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterStage2SelectedSymbol)

    logger = _MemoryLogger()
    state = _base_state(logger)
    state["commander_decision"] = {
        "market_regime": "neutral",
        "session_bias": "scanner_selected",
        "risk_mode": "balanced",
        "command_intent": "REFRESH_STRATEGY_FRAME",
        "strategist_invocation": "RUN_REFRESH",
        "llm_policy": "allow_context_refresh",
        "strategist_refresh_requested": True,
        "strategist_refresh_reason": "selected_symbol_tactical_refresh",
        "strategist_refresh_context": {
            "refresh_scope": "selected_symbol_tactical_refresh",
            "selected_symbol": "005930",
            "selected_rank": 1,
            "selected_score": 0.91,
            "scanner_primary_candidate": {"rank": 1, "symbol": "005930", "score": 0.91},
            "scanner_runner_ups": [
                {"rank": 2, "symbol": "000660", "score": 0.84},
                {"rank": 3, "symbol": "035420", "score": 0.80},
            ],
        },
    }
    state["reports_root"] = "reports"

    out = strategist_node(state)

    strategist_output = out.get("strategist_output") or {}
    stage2 = strategist_output.get("selected_symbol_tactical_review") or {}
    assert stage2["selected_symbol_decision"] == "cascade_to_runner_up"
    assert stage2["runner_up_order"] == ["000660", "035420"]
    assert strategist_output["selected_symbol_decision"] == "cascade_to_runner_up"
    assert strategist_output["commander_actionability"] == "policy_delta_allowed"

    watch_policy = strategist_output.get("candidate_watch_policy") or {}
    assert watch_policy["max_priority_rank"] == 3
    assert watch_policy["max_runner_ups"] == 2
    assert watch_policy["cascade_enabled"] is True

    directives = strategist_output.get("strategy_adjustment_directives") or {}
    assert directives["entry_policy_action"]["action"] == "tighten"
    assert "confidence_threshold" in directives["entry_policy_action"]["target_fields"]


def test_strategist_refresh_uses_persisted_selected_symbol_memory_when_not_in_read_model_facts(monkeypatch):
    captured = {}

    def fake_run_strategist_frame_llm(*, state, policy, payload):
        captured["payload"] = dict(payload or {})
        return ({}, {"status": "disabled", "attempts": 0, "repair_used": False, "reason": "test_capture"})

    monkeypatch.setenv("DRY_RUN", "1")
    monkeypatch.setattr("graphs.nodes.strategist_node._run_strategist_frame_llm", fake_run_strategist_frame_llm)

    logger = _MemoryLogger()
    state = _base_state(logger)
    state["candidate_symbols"] = ["005930"]
    state["commander_decision"] = {
        "market_regime": "neutral",
        "session_bias": "position_management",
        "risk_mode": "balanced",
        "command_intent": "REFRESH_STRATEGY_FRAME",
        "strategist_invocation": "RUN_REFRESH",
        "llm_policy": "allow_context_refresh",
        "strategist_refresh_requested": True,
        "strategist_refresh_reason": "selected_symbol_refresh",
        "open_position_refresh_context": {
            "refresh_scope": "open_position_monitor_refresh",
            "selected_symbol": "000660",
            "monitor_reason": "below_vwap_reclaim_not_ready",
            "refresh_summary": "Selected symbol refresh for 000660.",
            "entry_state": {"current_blocking_axis": "reclaim_readiness"},
        },
    }
    state["reports_root"] = "reports"

    def fake_build_symbol_read_model(trades_root, symbol, persisted_only=False):
        if symbol == "000660":
            return {
                "symbol": "000660",
                "trade_count": 11,
                "closed_trade_count": 9,
                "win_rate": 0.5555,
                "avg_pnl_pct": 0.0123,
                "avg_hold_duration_sec": 420.0,
                "dominant_playbook": "pullback",
                "dominant_monitor_blocker": "below_vwap_reclaim_not_ready",
                "dominant_exit_reason": "peak_drawdown",
                "repeated_failure_pattern": [
                    {"type": "blocker", "value": "below_vwap_reclaim_not_ready", "count": 3},
                ],
                "recent_success_pattern": [
                    {"playbook": "pullback", "entry_reason": "pullback_ok", "exit_reason": "take_profit", "count": 2},
                ],
                "data_quality": {"data_source": "symbol_memory", "unknown_fields_ratio": 0.0},
            }
        return {}

    monkeypatch.setattr("graphs.nodes.strategist_node.build_symbol_read_model", fake_build_symbol_read_model)

    strategist_node(state)

    llm_payload = dict(captured.get("payload") or {})
    commander_refresh_context = dict(llm_payload.get("commander_refresh_context") or {})
    assert commander_refresh_context["selected_symbol"] == "000660"
    assert commander_refresh_context["selected_symbol_memory"]["symbol"] == "000660"
    assert commander_refresh_context["selected_symbol_memory"]["dominant_playbook"] == "pullback"
    assert commander_refresh_context["selected_symbol_memory"]["dominant_monitor_blocker"] == "below_vwap_reclaim_not_ready"


def test_strategist_policy_adjustment_surface_tracks_delta(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    out = strategist_node(
        {
            "runtime_phase": "session",
            "candidate_symbols": ["111111", "222222", "333333"],
            "commander_decision": {
                "market_regime": "neutral",
                "session_bias": "position_management",
                "risk_mode": "balanced",
                "command_intent": "REFRESH_STRATEGY_FRAME",
                "strategist_invocation": "RUN_REFRESH",
                "llm_policy": "allow_context_refresh",
                "strategist_refresh_requested": True,
                "strategist_refresh_reason": "repeated_hold_monitor_only",
                "strategist_refresh_context": {
                    "prior_monitor_entry_policy_summary": {"volume_ratio_min": 0.68, "pullback_max_pct": 0.07},
                    "current_monitor_entry_policy_summary": {"volume_ratio_min": 0.68, "pullback_max_pct": 0.07},
                },
                "open_position_refresh_context": {
                    "refresh_scope": "open_position_monitor_refresh",
                    "selected_symbol": "111111",
                    "hold_repeat_count_max": 3,
                    "selected_hold_repeat_count": 3,
                    "monitor_reason": "too_extended_from_vwap",
                    "active_exit_axis": "peak_drawdown",
                    "refresh_summary": "Repeated hold refresh for 111111 after 3 consecutive hold cycles.",
                    "entry_state": {"current_blocking_axis": "reclaim_readiness", "entry_blockers": ["below_vwap_reclaim_not_ready"]},
                },
            },
            "ai_strategist_output": {
                "playbook": "pullback",
                "monitor_entry_policy": {
                    "volume_ratio_min": 0.75,
                    "pullback_max_pct": 0.05,
                },
                "policy_adjustment": {
                    "adjustment_required": True,
                    "dominant_failure_pattern": "repeated_hold_monitor_only",
                    "addressed_failure_patterns": ["below_vwap_reclaim_not_ready"],
                },
                "strategy_adjustment_directives": {
                    "entry_policy_action": {
                        "action": "tighten",
                        "target_fields": ["volume_ratio_min", "pullback_max_pct"],
                        "reason": "반복 hold 패턴으로 진입 조건을 조입니다",
                    }
                },
                "policy_source": "strategist",
            },
        }
    )

    adjustment = ((out.get("strategist_output") or {}).get("policy_adjustment") or {})
    assert adjustment.get("adjustment_required") is True
    assert adjustment.get("hold_refresh_considered") is True
    assert adjustment.get("delta_count") == 2
    assert "volume_ratio_min" in list(adjustment.get("delta_fields") or [])
    assert "pullback_max_pct" in list(adjustment.get("delta_fields") or [])
    directives = ((out.get("strategist_output") or {}).get("strategy_adjustment_directives") or {})
    assert ((directives.get("entry_policy_action") or {}).get("action")) == "tighten"
    assert "volume_ratio_min" in list((directives.get("entry_policy_action") or {}).get("target_fields") or [])


def test_strategist_directives_fallback_tracks_memory_and_policy(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "1")
    out = strategist_node(
        {
            "runtime_phase": "session",
            "candidate_symbols": ["111111", "222222"],
            "commander_decision": {
                "market_regime": "neutral",
                "session_bias": "position_management",
                "risk_mode": "balanced",
                "command_intent": "REFRESH_STRATEGY_FRAME",
                "strategist_invocation": "RUN_REFRESH",
                "llm_policy": "allow_context_refresh",
                "strategist_refresh_requested": True,
                "strategist_refresh_reason": "repeated_hold_monitor_only",
                "strategist_refresh_context": {
                    "prior_monitor_entry_policy_summary": {"volume_ratio_min": 0.68},
                    "current_monitor_entry_policy_summary": {"volume_ratio_min": 0.68},
                },
                "open_position_refresh_context": {
                    "refresh_scope": "open_position_monitor_refresh",
                    "selected_symbol": "111111",
                    "hold_repeat_count_max": 3,
                    "selected_hold_repeat_count": 3,
                    "monitor_reason": "too_extended_from_vwap",
                    "active_exit_axis": "peak_drawdown",
                    "refresh_summary": "Repeated hold refresh for 111111 after 3 consecutive hold cycles.",
                    "entry_state": {"current_blocking_axis": "reclaim_readiness", "entry_blockers": ["below_vwap_reclaim_not_ready"]},
                },
            },
            "ai_strategist_output": {
                "playbook": "breakout",
                "monitor_entry_policy": {
                    "volume_ratio_min": 0.75,
                    "pullback_max_pct": 0.05,
                },
                "policy_adjustment": {
                    "adjustment_required": True,
                    "dominant_failure_pattern": "below_vwap_reclaim_not_ready",
                    "addressed_failure_patterns": ["below_vwap_reclaim_not_ready"],
                },
                "policy_source": "strategist",
            },
            "reports_root": "reports",
        }
    )
    directives = ((out.get("strategist_output") or {}).get("strategy_adjustment_directives") or {})
    assert ((directives.get("playbook_action") or {}).get("action")) in {"maintain", "prefer", "deprioritize", "switch"}
    assert ((directives.get("entry_policy_action") or {}).get("action")) == "tighten"
    assert ((directives.get("monitor_focus_action") or {}).get("action")) == "increase_focus"
    assert "reclaim" in list((directives.get("monitor_focus_action") or {}).get("target_axes") or [])
    assert ((directives.get("selected_symbol_bias_action") or {}).get("action")) in {
        "none",
        "prefer_pullback",
        "avoid_breakout",
        "prefer_reclaim",
        "avoid_extension",
    }
    assert ((directives.get("refresh_action") or {}).get("action")) == "refresh_for_repeated_hold"


def test_strategist_frame_llm_max_tokens_falls_back_to_ai_strategist_setting(monkeypatch):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterCapturePolicy)

    logger = _MemoryLogger()
    state = _base_state(logger)
    state["policy"] = {
        "applied_policy": {
            "llm": {
                "strategist": {
                    "execution_profile": {
                        "name": "balanced_reasoning",
                        "max_tokens": 320,
                    }
                }
            }
        }
    }
    strategist_node(state)

    assert isinstance(_FakeRouterCapturePolicy.last_policy, dict)
    assert int(_FakeRouterCapturePolicy.last_policy.get("max_tokens") or 0) == 320


def test_strategist_frame_llm_timeout_falls_back_to_ai_strategist_setting(monkeypatch):
    monkeypatch.setenv("STRATEGIST_FRAME_USE_LLM", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setattr("graphs.nodes.strategist_node.LLMRouter", _FakeRouterCapturePolicy)

    logger = _MemoryLogger()
    state = _base_state(logger)
    state["policy"] = {
        "applied_policy": {
            "llm": {
                "strategist": {
                    "execution_profile": {
                        "name": "balanced_reasoning",
                        "timeout_sec": 15,
                    }
                }
            }
        }
    }
    strategist_node(state)

    assert isinstance(_FakeRouterCapturePolicy.last_policy, dict)
    assert float(_FakeRouterCapturePolicy.last_policy.get("timeout_sec") or 0.0) == 15.0


def test_strategist_frame_llm_missing_config_blocks_runtime(monkeypatch):
    monkeypatch.delenv("STRATEGIST_FRAME_USE_LLM", raising=False)
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.delenv("AI_STRATEGIST_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("AI_STRATEGIST_ENDPOINT", raising=False)
    monkeypatch.setenv("DRY_RUN", "false")

    logger = _MemoryLogger()
    out = strategist_node(_base_state(logger))

    strategist_output = out.get("strategist_output") or {}
    strategist_llm = out.get("strategist_llm") or {}
    assert strategist_output.get("llm_frame_status") == "unavailable"
    assert strategist_output.get("llm_frame_blocked") is True
    assert strategist_output.get("llm_frame_blocked_reason") == "strategist_llm_required"
    assert strategist_llm.get("blocked") is True
    assert strategist_llm.get("blocked_reason") == "strategist_llm_required"
