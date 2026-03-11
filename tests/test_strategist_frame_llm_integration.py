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
