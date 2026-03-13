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
    scanner_source_policy = strategist_output.get("scanner_source_policy") or {}
    assert scanner_source_policy.get("include_condition_search") is False
    assert isinstance(out.get("scanner_guidance"), dict)
    assert str((out.get("scanner_guidance") or {}).get("playbook") or "") in ("breakout", "pullback", "reversal", "defensive")


def test_strategist_condition_search_source_requires_explicit_opt_in(monkeypatch):
    from graphs.nodes.strategist_node import _scanner_source_policy

    monkeypatch.delenv("KIWOOM_CANDIDATE_ENABLE_CONDITION_SEARCH", raising=False)
    base = _scanner_source_policy(
        playbook="breakout",
        risk_tone="aggressive",
        trade_aggressiveness="high",
        market_regime="risk_on",
        themes=["semiconductor"],
    )
    assert base["include_condition_search"] is False
    assert "condition_search" not in list(base.get("preferred_sources") or [])

    monkeypatch.setenv("KIWOOM_CANDIDATE_ENABLE_CONDITION_SEARCH", "true")
    enabled = _scanner_source_policy(
        playbook="breakout",
        risk_tone="aggressive",
        trade_aggressiveness="high",
        market_regime="risk_on",
        themes=["semiconductor"],
    )
    assert enabled["include_condition_search"] is True
    assert "condition_search" in list(enabled.get("preferred_sources") or [])


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
    scanner_source_policy = strategist_output.get("scanner_source_policy") or {}
    assert scanner_source_policy.get("include_change_rate") is False
    assert scanner_source_policy.get("include_condition_search") is False
    assert scanner_source_policy.get("preferred_sources") == [
        "top_value",
        "top_volume",
        "sector_theme",
        "operator_watchlist",
    ]


def test_strategist_collects_market_news_queries_without_candidate_symbols(monkeypatch):
    captured_queries = []

    monkeypatch.setattr(
        "graphs.nodes.strategist_node.compute_global_sentiment_signal",
        lambda **_: {"score": 0.42, "status": "ok", "source": "mock_global", "reason": "", "ts": 1},
    )

    def _fake_collect(symbols, **_kwargs):
        captured_queries.append(list(symbols or []))
        return {
            str(s): [{"title": f"{s} headline", "source": "naver", "published_at": "2026-03-12T00:00:00Z"}]
            for s in list(symbols or [])
        }

    monkeypatch.setattr("graphs.nodes.strategist_node.collect_news_items", _fake_collect)
    monkeypatch.setattr(
        "graphs.nodes.strategist_node.score_news_sentiment_signal",
        lambda _items, symbols, **_: {
            str(s): {"score": 0.25, "status": "ok", "source": "mock_news", "reason": "", "ts": 1}
            for s in list(symbols or [])
        },
    )

    state = {
        "run_id": "srq-market-news",
        "policy": {
            "use_global_sentiment": True,
            "use_news_analysis": True,
            "use_universe_builder": False,
        },
        "market_context": {
            "index_trend": 0.20,
            "realized_volatility": 0.018,
            "market_breadth": 0.35,
            "macro_risk": 0.25,
        },
    }

    out = strategist_node(state)
    strategist_output = out.get("strategist_output") or {}
    news_query_targets = out.get("news_query_targets") or []

    assert out.get("candidate_symbols") == []
    assert isinstance(news_query_targets, list) and len(news_query_targets) > 0
    assert captured_queries and captured_queries[0] == news_query_targets
    assert strategist_output.get("news_query_targets") == news_query_targets
    assert "news_query_reasoning" in strategist_output
    assert "risk-on context" in str(strategist_output.get("news_query_reasoning") or "")
    assert int(((strategist_output.get("market_news_context") or {}).get("headline_count")) or 0) > 0
    assert int(((strategist_output.get("news_context") or {}).get("market_headline_count")) or 0) > 0


def test_strategist_news_query_targets_expand_theme_and_macro_context(monkeypatch):
    captured_queries = []

    monkeypatch.setattr(
        "graphs.nodes.strategist_node.compute_global_sentiment_signal",
        lambda **_: {"score": -0.35, "status": "ok", "source": "mock_global", "reason": "", "ts": 1},
    )

    def _fake_collect(symbols, **_kwargs):
        captured_queries.append(list(symbols or []))
        return {str(s): [] for s in list(symbols or [])}

    monkeypatch.setattr("graphs.nodes.strategist_node.collect_news_items", _fake_collect)
    monkeypatch.setattr(
        "graphs.nodes.strategist_node.score_news_sentiment_signal",
        lambda _items, symbols, **_: {
            str(s): {"score": 0.0, "status": "fallback", "source": "mock_news", "reason": "", "ts": 1}
            for s in list(symbols or [])
        },
    )

    state = {
        "themes": ["semiconductor", "AI"],
        "macro_events": ["FOMC", "중동 긴장"],
        "market_context": {
            "index_trend": -0.15,
            "realized_volatility": 0.032,
            "market_breadth": -0.20,
            "macro_risk": 0.80,
        },
        "policy": {
            "use_global_sentiment": True,
            "use_news_analysis": True,
            "use_universe_builder": False,
        },
    }

    out = strategist_node(state)
    targets = out.get("news_query_targets") or []

    assert captured_queries and captured_queries[0] == targets
    assert "중동" in targets
    assert "국제유가" in targets
    assert "반도체" in targets
    assert "AI" in targets
    reasoning = str((out.get("strategist_output") or {}).get("news_query_reasoning") or "")
    assert "risk-off macro context" in reasoning
    assert "semiconductor" in reasoning
    assert "AI" in reasoning


def test_strategist_news_query_targets_become_defensive_when_vix_is_elevated(monkeypatch):
    captured_queries = []

    monkeypatch.setattr(
        "graphs.nodes.strategist_node.compute_global_sentiment_signal",
        lambda **_: {
            "score": -0.05,
            "status": "ok",
            "source": "mock_global",
            "reason": "",
            "ts": 1,
            "fear_index": {
                "provider": "mock",
                "ticker": "^VIX",
                "level": 28.4,
                "change_pct": 2.2,
                "neutral_level": 20.0,
                "level_pressure": 0.42,
            },
        },
    )

    def _fake_collect(symbols, **_kwargs):
        captured_queries.append(list(symbols or []))
        return {str(s): [] for s in list(symbols or [])}

    monkeypatch.setattr("graphs.nodes.strategist_node.collect_news_items", _fake_collect)
    monkeypatch.setattr(
        "graphs.nodes.strategist_node.score_news_sentiment_signal",
        lambda _items, symbols, **_: {
            str(s): {"score": 0.0, "status": "fallback", "source": "mock_news", "reason": "", "ts": 1}
            for s in list(symbols or [])
        },
    )

    state = {
        "themes": ["AI"],
        "market_context": {
            "index_trend": -0.02,
            "realized_volatility": 0.02,
            "market_breadth": -0.05,
            "macro_risk": 0.30,
        },
        "policy": {
            "use_global_sentiment": True,
            "use_news_analysis": True,
            "use_universe_builder": False,
        },
    }

    out = strategist_node(state)
    targets = out.get("news_query_targets") or []
    reasoning = str((out.get("strategist_output") or {}).get("news_query_reasoning") or "")

    assert captured_queries and captured_queries[0] == targets
    assert "국제유가" in targets
    assert "환율" in targets
    assert "금" in targets
    assert "중동" in targets
    assert "elevated fear index" in reasoning
    assert "vix=28.40" in reasoning
