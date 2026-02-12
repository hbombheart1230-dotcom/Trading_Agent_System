from graphs.nodes.decide_trade import decide_trade

def test_provider_openai_fallback_when_missing_endpoint(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.delenv("AI_STRATEGIST_ENDPOINT", raising=False)
    monkeypatch.setenv("AI_STRATEGIST_MODEL", "gpt-x")

    state = {
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2000000, "open_positions": 0},
    }
    out = decide_trade(state)

    # Missing endpoint -> RuleStrategist fallback (may BUY depending on rule)
    assert out["decision_trace"]["strategy"] in ("RuleStrategist", "builtin_rule")
    assert out["decision_packet"]["intent"]["action"] in ("BUY", "NOOP")
