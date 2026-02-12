from graphs.nodes.decide_trade import decide_trade

def test_openai_provider_success_via_monkeypatch(monkeypatch):
    monkeypatch.setenv("AI_STRATEGIST_PROVIDER", "openai")
    monkeypatch.setenv("AI_STRATEGIST_API_KEY", "dummy")
    monkeypatch.setenv("AI_STRATEGIST_ENDPOINT", "https://example.invalid/strategist")
    monkeypatch.setenv("AI_STRATEGIST_MODEL", "test-model")

    import libs.ai.providers.openai_provider as prov

    def fake_post_json(url, headers, payload, timeout=15.0):
        return {"intent": {"action": "NOOP", "reason": "test"}, "rationale": "ok", "meta": {"url": url}}

    monkeypatch.setattr(prov, "_post_json", fake_post_json)

    state = {
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 2000000, "open_positions": 0},
    }
    out = decide_trade(state)
    assert out["decision_trace"]["strategy"] == "OpenAIStrategist"
    assert out["decision_packet"]["intent"]["action"] == "NOOP"
