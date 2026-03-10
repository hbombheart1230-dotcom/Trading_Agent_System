from __future__ import annotations

from graphs.nodes.strategist_node import strategist_node


def test_strategist_reasoning_uses_market_news_macro_context(monkeypatch):
    monkeypatch.setenv("TOP_N_CANDIDATES", "3")

    monkeypatch.setattr(
        "graphs.nodes.strategist_node.compute_global_sentiment_signal",
        lambda **_: {"score": 0.65, "status": "ok", "source": "mock_global", "reason": "", "ts": 1},
    )
    monkeypatch.setattr(
        "graphs.nodes.strategist_node.collect_news_items",
        lambda symbols, **_: {str(s): [{"title": f"{s} momentum strong"}] for s in list(symbols or [])},
    )
    monkeypatch.setattr(
        "graphs.nodes.strategist_node.score_news_sentiment_signal",
        lambda _items, symbols, **_: {
            str(s): {"score": 0.40, "status": "ok", "source": "mock_news", "reason": "", "ts": 1}
            for s in list(symbols or [])
        },
    )

    state = {
        "run_id": "srq-1",
        "themes": ["semiconductor", "AI"],
        "theme_scores": {"semiconductor": 0.8, "AI": 0.7},
        "theme_map": {"semiconductor": ["005930", "000660"], "ai": ["042700"]},
        "candidate_symbols": ["005930", "000660", "042700"],
        "macro_events": ["FOMC dovish tone", "USD weakness"],
        "market_context": {
            "index_trend": 0.45,
            "realized_volatility": 0.018,
            "market_breadth": 0.62,
            "macro_risk": 0.20,
        },
        "kiwoom_market_summary": {"market_breadth": 0.58},
        "policy": {
            "use_global_sentiment": True,
            "use_news_analysis": True,
            "use_universe_builder": False,
        },
    }

    out = strategist_node(state)
    strategist_output = out.get("strategist_output") or {}
    assert strategist_output.get("market_regime") == "risk_on"
    assert strategist_output.get("market_sentiment") == "bullish"
    assert strategist_output.get("playbook") in ("breakout", "pullback")
    assert isinstance(strategist_output.get("key_events"), list) and len(strategist_output.get("key_events") or []) > 0
    assert isinstance(strategist_output.get("theme_strength"), dict)
    assert float(strategist_output.get("regime_score") or 0.0) > 0.0
    assert float(strategist_output.get("sentiment_score") or 0.0) > 0.0
    assert isinstance(out.get("scanner_guidance"), dict)
    assert str((out.get("scanner_guidance") or {}).get("playbook") or "") in ("breakout", "pullback", "reversal", "defensive")


def test_strategist_reasoning_becomes_defensive_on_risk_off_context(monkeypatch):
    monkeypatch.setenv("TOP_N_CANDIDATES", "3")
    monkeypatch.setattr(
        "graphs.nodes.strategist_node.compute_global_sentiment_signal",
        lambda **_: {"score": -0.70, "status": "ok", "source": "mock_global", "reason": "", "ts": 1},
    )
    monkeypatch.setattr(
        "graphs.nodes.strategist_node.collect_news_items",
        lambda symbols, **_: {str(s): [] for s in list(symbols or [])},
    )
    monkeypatch.setattr(
        "graphs.nodes.strategist_node.score_news_sentiment_signal",
        lambda _items, symbols, **_: {
            str(s): {"score": -0.50, "status": "ok", "source": "mock_news", "reason": "", "ts": 1}
            for s in list(symbols or [])
        },
    )

    state = {
        "themes": ["semiconductor"],
        "candidate_symbols": ["005930", "000660", "042700"],
        "market_context": {
            "index_trend": -0.40,
            "realized_volatility": 0.050,
            "market_breadth": -0.70,
            "macro_risk": 0.90,
        },
        "policy": {
            "use_global_sentiment": True,
            "use_news_analysis": True,
            "use_universe_builder": False,
        },
    }

    out = strategist_node(state)
    strategist_output = out.get("strategist_output") or {}
    assert strategist_output.get("market_regime") == "risk_off"
    assert strategist_output.get("playbook") == "defensive"
    assert strategist_output.get("risk_tone") == "conservative"
    avoid_themes = strategist_output.get("avoid_themes") or []
    assert "high_gap_speculative" in avoid_themes
