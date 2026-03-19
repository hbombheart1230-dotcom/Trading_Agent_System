from libs.reporting.trade_story_pipeline import (
    build_market_context_human,
    build_monitor_reason_human,
    build_scanner_reason_human,
    enrich_scanner_reason_from_evidence,
)


def test_market_context_human_prefers_strategist_input_summary_when_runtime_fields_missing() -> None:
    out = build_market_context_human(
        {
            "market_regime": "neutral",
            "market_sentiment": "neutral",
            "playbook": "breakout",
            "themes": ["broad_market_leaders", "defensive_large_cap"],
            "macro_stress_overlay": {"stress_flags": ["elevated_vix", "yield_rise"], "active": True},
            "input_summary": {
                "global_sentiment_score": -0.2235,
                "vix_level": 25.09,
                "vix_change_pct": 12.16,
                "vix_level_pressure": 0.255,
                "headline_count": 75,
                "candidate_signal_total": 5,
                "market_signal_total": 10,
                "news_query_targets": ["코스피", "미국 증시", "국제유가", "환율"],
                "key_events_hint": [
                    "global_sentiment score=-0.224 status=ok source=yfinance",
                    "fear_index vix=25.09 change=12.16% pressure=0.255",
                ],
            },
        }
    )

    assert out["global_sentiment_score"] == -0.2235
    assert out["vix_level"] == 25.09
    assert out["headline_count"] == 75
    assert out["news_query_count"] == 4
    assert out["market_signal_total"] == 10
    assert out["candidate_signal_total"] == 5
    assert out["news_query_targets"] == ["코스피", "미국 증시", "국제유가", "환율"]
    assert "75 headlines were considered across 4 targets" in out["news_input_summary"]
    assert any("News query targets: 코스피, 미국 증시, 국제유가, 환율" in row for row in out["bullets"])


def test_scanner_reason_human_surfaces_top_candidates_and_runner_up_deltas() -> None:
    out = build_scanner_reason_human(
        {
            "universe_size": 5,
            "selected_symbol": "000660",
            "ranking_table": [
                {"rank": 1, "symbol": "000660", "score_total": 1.1776, "risk_score": 0.6281, "confidence": 0.8099},
                {"rank": 2, "symbol": "005930", "score_total": 1.1519, "risk_score": 0.7310, "confidence": 0.7851},
                {"rank": 3, "symbol": "047040", "score_total": 1.1408, "risk_score": 0.9130, "confidence": 0.7638},
            ],
            "selected_candidate": {
                "symbol": "000660",
                "sources": ["top_value", "sector_theme"],
                "score_total": 1.1776,
                "risk_score": 0.6281,
                "confidence": 0.8099,
                "score_breakdown": {"trading_value": 0.22, "theme_boost": 0.0624},
                "feature_snapshot": {"engine_ma20_gap": 0.05, "engine_adx14": 13.17, "engine_trend_strength": 0.13},
            },
            "candidate_preview": [
                {"symbol": "005930", "why": "weaker sector fit"},
                {"symbol": "047040", "why": "higher volatility and lower confidence"},
            ],
        },
        {"playbook": "breakout"},
    )

    assert out["selected_symbol"] == "000660"
    assert out["selected_rank"] == 1
    assert out["selected_score"] == 1.1776
    assert len(out["top_candidates"]) == 3
    assert out["runner_ups"][0]["symbol"] == "005930"
    assert "score gap" in out["runner_ups"][0]["why"]
    assert any("Top candidates:" in row for row in out["bullets"])
    assert any("Why not others:" in row for row in out["bullets"])


def test_monitor_reason_human_keeps_normalized_exit_context_details() -> None:
    out = build_monitor_reason_human(
        {
            "trigger_type": "hard_stop",
            "monitor_reason": "confirmed_exit_signal",
            "thresholds_guards_used": {
                "thresholds": {
                    "stop_loss_pct": 0.08,
                    "effective_stop_loss_pct": 0.01,
                    "effective_stop_reason": "hard_stop",
                    "take_profit_pct": 0.0084,
                    "peak_drawdown_exit_pct": 0.0052,
                },
                "exit_confirm_ticks": 3,
                "exit_confirm_count": 2,
            },
            "exit_triggered": True,
            "current_price": 29300.0,
            "average_price": 29650.0,
            "peak_price": 29650.0,
            "current_drawdown": -0.0118,
            "active_exit_axis": "Hard Stop",
            "watch_axes": ["Hard stop", "Take profit", "Trailing stop"],
            "price_source": "position.current_price",
            "feature_source": "selected.features",
            "decision_reason_chain": ["hold", "hard_stop", "confirmed_exit_signal"],
        },
        {"action": "SELL"},
    )

    assert out["posture"] == "SELL"
    assert out["trigger_type"] == "hard_stop"
    assert out["active_exit_axis"] == "Hard Stop"
    assert out["effective_stop_loss_pct"] == 0.01
    assert out["confirm_required"] == 3
    assert out["confirm_count"] == 2
    assert out["watch_axes"][:3] == ["Hard stop", "Take profit", "Trailing stop"]
    assert "hard_stop" in out["summary"]
    assert any("Exit confirmation: 2/3" in row for row in out["bullets"])


def test_enrich_scanner_reason_from_evidence_promotes_selection_reason_details() -> None:
    out = enrich_scanner_reason_from_evidence(
        {
            "summary": "Scanner selected 000660 as rank #1.",
            "bullets": ["Universe scanned: 5"],
        },
        {
            "candidate_selection_reasons": [
                {
                    "payload": {
                        "why_selected": [
                            "highest total score (1.178)",
                            "confidence 0.81 and risk 0.63",
                        ],
                        "runner_ups_lost": [
                            {
                                "symbol": "005930",
                                "why_lost": [
                                    "lower total score (1.152 vs 1.178)",
                                    "higher risk (0.73 vs 0.63)",
                                ],
                            }
                        ],
                        "tie_break_rule": "score_total desc -> confidence desc -> risk_score asc",
                        "final_decision_basis": "Scanner selected the highest-ranked candidate after strategist-guided weighting.",
                    }
                }
            ]
        },
    )

    assert out["selection_basis"] == "Scanner selected the highest-ranked candidate after strategist-guided weighting."
    assert out["tie_break_rule"] == "score_total desc -> confidence desc -> risk_score asc"
    assert out["why_selected"][0] == "highest total score (1.178)"
    assert out["runner_ups_lost"][0]["symbol"] == "005930"
    assert any("Selection decision:" in row for row in out["bullets"])
