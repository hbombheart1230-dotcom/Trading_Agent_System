from __future__ import annotations

from graphs.nodes.strategist_node import _exit_policy, _global_sentiment_breakdown_payload, strategist_node


def test_strategist_exit_policy_uses_adaptive_playbook_baseline(monkeypatch):
    monkeypatch.delenv("EXIT_POLICY_STOP_LOSS_PCT", raising=False)
    monkeypatch.delenv("EXIT_POLICY_TAKE_PROFIT_PCT", raising=False)

    breakout = _exit_policy(
        playbook="breakout",
        monitor_guidance="hold_through_noise",
        trade_aggressiveness="high",
        risk_tone="aggressive",
    )
    defensive = _exit_policy(
        playbook="defensive",
        monitor_guidance="defensive_exit",
        trade_aggressiveness="low",
        risk_tone="conservative",
    )

    assert float(breakout.get("stop_loss_pct") or 0.0) > float(defensive.get("stop_loss_pct") or 0.0)
    assert float(breakout.get("take_profit_pct") or 0.0) > float(defensive.get("take_profit_pct") or 0.0)
    assert "baseline:breakout" in list(breakout.get("adjustments") or [])
    assert "baseline:defensive" in list(defensive.get("adjustments") or [])


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


def test_scanner_source_policy_becomes_more_defensive_when_fear_index_is_elevated(monkeypatch):
    from graphs.nodes.strategist_node import _scanner_source_policy

    monkeypatch.delenv("KIWOOM_CANDIDATE_ENABLE_CONDITION_SEARCH", raising=False)
    policy = _scanner_source_policy(
        playbook="breakout",
        risk_tone="aggressive",
        trade_aggressiveness="high",
        market_regime="risk_on",
        themes=["semiconductor"],
        fear_index={"level": 28.4, "level_pressure": 0.42},
    )
    assert policy["include_change_rate"] is False
    assert policy["include_condition_search"] is False
    assert "top_change_rate" not in list(policy.get("preferred_sources") or [])
    assert list(policy.get("preferred_sources") or [])[:3] == ["top_value", "sector_theme", "top_volume"]
    assert float(((policy.get("source_weights") or {}).get("top_value")) or 0.0) >= 2.3
    assert "elevated fear index" in str(policy.get("reason") or "")


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


def test_strategist_macro_stress_overlay_makes_monitor_frame_more_defensive(monkeypatch):
    monkeypatch.setattr(
        "graphs.nodes.strategist_node.compute_global_sentiment_signal",
        lambda **_: {
            "score": 0.55,
            "status": "ok",
            "source": "mock_global",
            "reason": "",
            "ts": 1,
            "macro_moves": {
                "vix_pct": 1.2,
                "vix_level": 29.0,
                "vix_level_pressure": 0.45,
                "dxy_pct": 0.35,
                "tnx_delta": 0.007,
            },
            "fear_index": {
                "provider": "mock",
                "ticker": "^VIX",
                "level": 29.0,
                "change_pct": 1.2,
                "neutral_level": 20.0,
                "level_pressure": 0.45,
            },
        },
    )
    monkeypatch.setattr(
        "graphs.nodes.strategist_node.collect_news_items",
        lambda symbols, **_: {str(s): [] for s in list(symbols or [])},
    )
    monkeypatch.setattr(
        "graphs.nodes.strategist_node.score_news_sentiment_signal",
        lambda _items, symbols, **_: {
            str(s): {"score": 0.2, "status": "ok", "source": "mock_news", "reason": "", "ts": 1}
            for s in list(symbols or [])
        },
    )

    state = {
        "themes": ["semiconductor"],
        "candidate_symbols": ["005930", "000660"],
        "market_context": {
            "index_trend": 0.45,
            "realized_volatility": 0.018,
            "market_breadth": 0.55,
            "macro_risk": 0.10,
        },
        "policy": {
            "use_global_sentiment": True,
            "use_news_analysis": True,
            "use_universe_builder": False,
        },
    }

    out = strategist_node(state)
    strategist_output = out.get("strategist_output") or {}
    overlay = strategist_output.get("macro_stress_overlay") or {}
    exit_policy = strategist_output.get("exit_policy") or {}

    assert strategist_output.get("market_regime") == "risk_on"
    assert strategist_output.get("playbook") == "breakout"
    assert strategist_output.get("monitor_guidance") == "defensive_exit"
    assert strategist_output.get("risk_tone") == "conservative"
    assert strategist_output.get("trade_aggressiveness") == "low"
    assert overlay.get("active") is True
    assert overlay.get("intensity") == "high"
    assert "elevated_vix" in list(overlay.get("stress_flags") or [])
    assert "dollar_strength" in list(overlay.get("stress_flags") or [])
    assert "yield_rise" in list(overlay.get("stress_flags") or [])
    assert "macro_stress:tightened_exit_policy" in list(overlay.get("adjustments") or [])
    assert "macro_stress" in list(strategist_output.get("report_focus") or [])


def test_strategist_macro_stress_overlay_moderates_but_does_not_hard_override(monkeypatch):
    monkeypatch.setattr(
        "graphs.nodes.strategist_node.compute_global_sentiment_signal",
        lambda **_: {
            "score": 0.55,
            "status": "ok",
            "source": "mock_global",
            "reason": "",
            "ts": 1,
            "macro_moves": {
                "vix_pct": 1.2,
                "vix_level": 27.0,
                "vix_level_pressure": 0.35,
                "dxy_pct": 0.35,
                "tnx_delta": 0.002,
            },
            "fear_index": {
                "provider": "mock",
                "ticker": "^VIX",
                "level": 27.0,
                "change_pct": 1.2,
                "neutral_level": 20.0,
                "level_pressure": 0.35,
            },
        },
    )
    monkeypatch.setattr(
        "graphs.nodes.strategist_node.collect_news_items",
        lambda symbols, **_: {str(s): [] for s in list(symbols or [])},
    )
    monkeypatch.setattr(
        "graphs.nodes.strategist_node.score_news_sentiment_signal",
        lambda _items, symbols, **_: {
            str(s): {"score": 0.2, "status": "ok", "source": "mock_news", "reason": "", "ts": 1}
            for s in list(symbols or [])
        },
    )

    state = {
        "themes": ["semiconductor"],
        "candidate_symbols": ["005930", "000660"],
        "market_context": {
            "index_trend": 0.45,
            "realized_volatility": 0.018,
            "market_breadth": 0.55,
            "macro_risk": 0.10,
        },
        "policy": {
            "use_global_sentiment": True,
            "use_news_analysis": True,
            "use_universe_builder": False,
        },
    }

    out = strategist_node(state)
    strategist_output = out.get("strategist_output") or {}
    overlay = strategist_output.get("macro_stress_overlay") or {}

    assert strategist_output.get("market_regime") == "risk_on"
    assert strategist_output.get("playbook") == "breakout"
    assert strategist_output.get("monitor_guidance") == "hold_through_noise"
    assert strategist_output.get("risk_tone") == "normal"
    assert strategist_output.get("trade_aggressiveness") == "medium"
    assert overlay.get("active") is True
    assert overlay.get("intensity") == "moderate"
    assert "macro_stress:risk_tone=normal" in list(overlay.get("adjustments") or [])


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
    assert "\ud558\ub77d \uc885\ubaa9 \uc218" in news_query_targets
    assert "\uc57d\uc138 \uc5c5\uc885" in news_query_targets
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
    assert "\uc911\ub3d9" in targets
    assert "\uad6d\uc81c\uc720\uac00" in targets
    assert "\ubc18\ub3c4\uccb4" in targets
    assert "AI" in targets
    assert "\ubcc0\ub3d9\uc131 \ud655\ub300" in targets
    reasoning = str((out.get("strategist_output") or {}).get("news_query_reasoning") or "")
    assert "risk-off macro context" in reasoning
    assert "intraday volatility added \ubcc0\ub3d9\uc131 \ud655\ub300 query" in reasoning
    assert "semiconductor" in reasoning
    assert "AI" in reasoning


def test_strategist_news_collection_reuses_kiwoom_theme_component_pool(monkeypatch):
    captured_queries = []

    def _fake_collect(symbols, **_kwargs):
        captured_queries.append(list(symbols or []))
        return {
            str(s): [{"title": f"{s} headline", "source": "naver", "published_at": "2026-04-28T00:00:00Z"}]
            for s in list(symbols or [])
        }

    monkeypatch.setattr("graphs.nodes.strategist_node.collect_news_items", _fake_collect)
    monkeypatch.setattr(
        "graphs.nodes.strategist_node.score_news_sentiment_signal",
        lambda _items, symbols, **_: {
            str(s): {"score": 0.1, "status": "ok", "source": "mock_news", "reason": "", "ts": 1}
            for s in list(symbols or [])
        },
    )
    monkeypatch.delenv("KIWOOM_THEME_LIVE_FETCH", raising=False)

    state = {
        "run_id": "srq-news-theme-components",
        "candidate_symbols": ["005930"],
        "mock_theme_groups": [
            {
                "thema_grp_cd": "400",
                "thema_nm": "semiconductor",
                "stk_num": "5",
                "flu_rt": "+4.0",
                "rising_stk_num": "4",
                "fall_stk_num": "0",
                "dt_prft_rt": "+12.0",
            }
        ],
        "mock_theme_component_map": {"semiconductor": ["005930", "000660", "042700"]},
        "policy": {
            "use_global_sentiment": False,
            "use_news_analysis": True,
            "use_universe_builder": False,
            "strategist_news_query_limit": 10,
        },
    }

    out = strategist_node(state)
    news_policy = out.get("news_collection_policy") or {}
    strategist_output = out.get("strategist_output") or {}

    assert "semiconductor" in (out.get("news_query_targets") or [])
    assert news_policy.get("provider") == "naver"
    assert news_policy.get("post_scanner_requery") is False
    assert news_policy.get("reuse_policy") == "reuse_pre_scanner_news_pool"
    assert "000660" in list(news_policy.get("theme_component_symbols_requested") or [])
    assert "000660" in list(news_policy.get("collection_symbols") or [])
    assert "000660" in list((out.get("news_sentiment_signal") or {}).keys())
    assert strategist_output.get("news_collection_policy", {}).get("post_scanner_requery") is False
    assert captured_queries and "000660" in captured_queries[0]


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
    assert "\uad6d\uc81c\uc720\uac00" in targets
    assert "\ud658\uc728" in targets
    assert "\ub2ec\ub7ec" in targets
    assert "\uc911\ub3d9" in targets
    assert "elevated fear index" in reasoning
    assert "vix=28.40" in reasoning


def test_global_sentiment_breakdown_uses_signed_effective_vix_contribution():
    payload = _global_sentiment_breakdown_payload(
        {
            "score": -0.22,
            "raw_score": -0.22,
            "status": "ok",
            "source": "mock_global",
            "weights": {
                "sp500": 0.30,
                "nasdaq": 0.35,
                "dow": 0.20,
                "vix": 0.10,
                "vix_level": 0.08,
                "dxy": 0.075,
                "tnx": 0.075,
                "vix_neutral_level": 20.0,
            },
            "components": {
                "sp500_ret": -0.01,
                "nasdaq_ret": -0.015,
                "dow_ret": -0.012,
                "vix_ret": 0.12,
                "vix_level": 25.0,
                "dxy_ret": 0.006,
                "tnx_delta": 0.005,
            },
            "fear_index": {
                "level": 25.0,
                "change_pct": 12.0,
                "neutral_level": 20.0,
                "level_pressure": 0.25,
            },
        }
    )

    contributions = {row["factor"]: row for row in payload["factor_contributions"]}
    vix_level = contributions["vix_level"]
    vix_ret = contributions["vix_ret"]

    assert vix_level["raw_value"] == 25.0
    assert vix_level["effective_value"] == 0.25
    assert vix_level["signed_effective_value"] == -0.25
    assert vix_level["weighted_contribution"] == -0.02
    assert vix_level["direction"] == "risk_off_pressure"
    assert "normalized vix_level_pressure" in vix_level["note"]

    assert vix_ret["raw_value"] == 0.12
    assert vix_ret["signed_effective_value"] == -0.12
    assert vix_ret["weighted_contribution"] == -0.012
