from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from graphs.nodes.strategist_node import strategist_node


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
