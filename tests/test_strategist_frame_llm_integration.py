from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

import pytest

from graphs.nodes.strategist_node import _build_compact_strategist_llm_payload, _build_strategist_llm_messages, strategist_node
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
    assert trace_payload.get("reporter_feedback_consumed") is True
    assert trace_payload.get("reporter_feedback_confidence") == "medium"


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


def test_strategist_reporter_feedback_mode_auto_ignores_missing_packet(monkeypatch):
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

    out = strategist_node(state)

    strategist_output = out.get("strategist_output") or {}
    assert strategist_output.get("playbook") == "breakout"
    assert strategist_output.get("themes") == ["semiconductor", "ai"]
    reporter_feedback = strategist_output.get("reporter_feedback_packet") or {}
    assert reporter_feedback.get("available") is False
    assert reporter_feedback.get("status") == "missing"
    assert reporter_feedback.get("reporter_feedback_mode") == "auto"
    assert reporter_feedback.get("reporter_feedback_mode_source") == "commander_applied_policy"
    assert reporter_feedback.get("feedback_gate_reason") == "no_packet"


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
    }

    compact = _build_compact_strategist_llm_payload(payload)

    assert compact["global_sentiment_signal"]["score"] == -0.1738
    assert len(compact["recent_strategy_feedback"]["top_recent_strengths"]) == 3
    assert len(compact["recent_strategy_feedback"]["top_recent_weaknesses"]) == 4
    assert len(compact["recent_strategy_feedback"]["suggested_report_focus"]) == 4
    assert compact["recent_strategy_feedback"]["recent_theme_performance"]["defense"]["appearance_count"] == 6
    assert compact["reporter_feedback_packet"]["available"] is True
    assert compact["reporter_feedback_packet"]["route_analysis"]["monitor_only_ratio"] == 0.6
    assert len(compact["reporter_feedback_packet"]["blocker_analysis"]) == 2
    assert len(compact["reporter_feedback_packet"]["recommendation"]) == 2
    assert len(compact["market_news_sample"]) == 4
    assert len(compact["candidate_news_sample"]) == 4
    assert len(compact["candidate_symbols_hint"]) == 5
    assert len(compact["key_events_hint"]) == 4
    assert len(compact["themes_hint"]) == 4
    assert len(compact["news_query_targets"]) == 8
    assert compact["commander_refresh_context"]["requested"] is True
    assert compact["commander_refresh_context"]["selected_symbol"] == "000660"
    assert compact["commander_refresh_context"]["requires_policy_delta"] is True
    assert compact["commander_refresh_context"]["selected_symbol_memory"]["symbol"] == "000660"
    assert compact["commander_refresh_context"]["selected_symbol_memory"]["dominant_playbook"] == "pullback"


def test_build_strategist_llm_messages_enforces_read_model_facts_and_policy_adjustment() -> None:
    messages = _build_strategist_llm_messages({"read_model_facts": {}, "commander_refresh_context": {}})

    system = str(messages[0]["content"])
    user = str(messages[1]["content"])

    assert "You MUST use the provided deterministic memory packets as primary constraints" in system
    assert "You MUST convert those inputs into explicit strategy adjustment directives." in system
    assert "strategy_adjustment_directives" in user
    assert "If repeated failure is concentrated in one axis" in user
    assert '"refresh_action"' in user


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
