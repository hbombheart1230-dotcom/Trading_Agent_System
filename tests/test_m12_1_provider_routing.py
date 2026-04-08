import pytest

from graphs.nodes.decide_trade import decide_trade


@pytest.fixture(autouse=True)
def _disable_strategy_v1(monkeypatch):
    monkeypatch.setenv("USE_STRATEGY_V1", "false")


def test_provider_openai_fallback_when_missing_endpoint(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.delenv("AI_STRATEGIST_ENDPOINT", raising=False)
    monkeypatch.setenv("AI_STRATEGIST_MODEL", "gpt-x")

    state = {
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2000000, "open_positions": 0},
        "applied_policy": {"strategist": {"runtime": {"strict_mode": True}}},
    }
    out = decide_trade(state)

    assert out["decision_trace"]["strategy"] == "BlockedStrategist"
    assert out["decision_packet"]["intent"]["action"] == "NOOP"
    assert out["decision_packet"]["intent"]["reason"] == "strategist_llm_required"


def test_provider_rule_is_blocked_when_legacy_runtime_disabled(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "rule")

    state = {
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2000000, "open_positions": 0},
        "applied_policy": {"strategist": {"runtime": {"allow_legacy_rule": False}}},
    }
    out = decide_trade(state)

    assert out["decision_trace"]["strategy"] == "BlockedStrategist"
    assert out["decision_packet"]["intent"]["action"] == "NOOP"
    assert out["decision_packet"]["intent"]["reason"] == "strategist_llm_required"
