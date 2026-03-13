from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from graphs.nodes.strategist_node import strategist_node
from libs.research.strategy_memory_store import save_strategy_feedback


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
    assert strategist_llm.get("attempts") == 2
    assert strategist_llm.get("repair_used") is True


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
    assert strategist_llm.get("attempts") == 2
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
    assert strategist_llm.get("attempts") == 2
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

    strategist_llm = out.get("strategist_llm") or {}
    assert strategist_llm.get("status") == "ok"
    assert strategist_llm.get("attempts") == 2
    assert strategist_llm.get("repair_used") is True


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
