from __future__ import annotations

from unittest.mock import patch

from graphs.nodes.scanner_node import scanner_node
from graphs.nodes.strategist_node import _default_policy, strategist_node


def test_strategist_emits_signal_contract_for_global_and_news_when_disabled():
    state = {
        "universe": ["AAA", "BBB"],
        "policy": {
            "candidate_k": 2,
            "use_global_sentiment": False,
            "use_news_analysis": False,
        },
    }
    out = strategist_node(state)

    assert "global_sentiment" in out and "score" in out["global_sentiment"]
    assert out["global_sentiment_signal"]["status"] == "fallback"
    assert out["global_sentiment_signal"]["reason"] == "global_sentiment_disabled"

    assert "news_sentiment" in out
    assert "news_sentiment_signal" in out
    assert out["news_sentiment_signal"]["AAA"]["status"] == "fallback"
    assert out["news_sentiment_signal"]["AAA"]["reason"] == "news_analysis_disabled"
    assert float(out["news_sentiment"]["AAA"]) == 0.0


def test_scanner_prefers_signal_score_over_legacy_news_score():
    state = {
        "candidates": [{"symbol": "AAA"}, {"symbol": "BBB"}],
        "mock_scan_results": {
            "AAA": {"score": 0.50, "risk_score": 0.10, "confidence": 0.80},
            "BBB": {"score": 0.50, "risk_score": 0.10, "confidence": 0.80},
        },
        # opposite legacy scores (should be ignored when signal is present)
        "news_sentiment": {"AAA": 1.0, "BBB": 0.0},
        "news_sentiment_signal": {
            "AAA": {"score": 0.0, "status": "ok", "source": "test", "reason": "", "ts": 1772812800},
            "BBB": {"score": 1.0, "status": "ok", "source": "test", "reason": "", "ts": 1772812800},
        },
        "policy": {
            "weight_news": 0.20,
            "weight_global": 0.0,
            "risk_news_penalty": 0.0,
            "risk_global_penalty": 0.0,
            "confidence_news_boost": 0.0,
        },
    }
    out = scanner_node(state)
    assert out["selected"]["symbol"] == "BBB"


def test_scanner_components_include_signal_status_fields():
    state = {
        "candidates": [{"symbol": "AAA"}],
        "mock_scan_results": {
            "AAA": {"score": 0.50, "risk_score": 0.10, "confidence": 0.80},
        },
        "global_sentiment_signal": {
            "score": 0.25,
            "status": "fallback",
            "source": "dry_run_policy",
            "reason": "dry_run_neutral",
            "ts": 1772812800,
        },
        "news_sentiment_signal": {
            "AAA": {
                "score": 0.10,
                "status": "unavailable",
                "source": "scorer:simple",
                "reason": "fetch_failed",
                "ts": 1772812800,
            }
        },
        "policy": {
            "weight_news": 0.0,
            "weight_global": 0.0,
            "risk_news_penalty": 0.0,
            "risk_global_penalty": 0.0,
            "confidence_news_boost": 0.0,
        },
    }
    out = scanner_node(state)
    comp = (out["selected"] or {}).get("components") or {}
    assert comp["news_sentiment_status"] == "unavailable"
    assert comp["global_sentiment_status"] == "fallback"
    assert comp["global_sentiment_reason"] == "dry_run_neutral"


def test_strategist_default_policy_reads_news_sentiment_env(monkeypatch):
    monkeypatch.setenv("M10_USE_NEWS_SENTIMENT", "true")
    p_true = _default_policy({})
    assert bool(p_true.get("use_news_analysis")) is True

    monkeypatch.setenv("M10_USE_NEWS_SENTIMENT", "false")
    p_false = _default_policy({})
    assert bool(p_false.get("use_news_analysis")) is False


def test_strategist_preserves_open_position_refresh_context_in_commander_ref():
    with patch(
        "graphs.nodes.strategist_node.build_symbol_read_model",
        return_value={
            "symbol": "322000",
            "trade_count": 8,
            "closed_trade_count": 7,
            "win_rate": 0.5,
            "avg_pnl_pct": 0.01,
            "avg_hold_duration_sec": 360.0,
            "dominant_playbook": "pullback",
            "dominant_monitor_blocker": "below_vwap_reclaim_not_ready",
            "dominant_exit_reason": "peak_drawdown",
            "repeated_failure_pattern": [
                {"type": "blocker", "value": "below_vwap_reclaim_not_ready", "count": 2},
            ],
            "recent_success_pattern": [
                {"playbook": "pullback", "entry_reason": "pullback_ok", "exit_reason": "take_profit", "count": 2},
            ],
            "data_quality": {"data_source": "symbol_memory", "unknown_fields_ratio": 0.0},
        },
    ):
        out = strategist_node(
            {
                "universe": ["322000"],
                "candidate_symbols": ["322000"],
                "policy": {
                    "candidate_k": 1,
                    "use_global_sentiment": False,
                    "use_news_analysis": False,
                },
                "commander_decision": {
                    "market_regime": "neutral",
                    "session_bias": "active_selection",
                    "risk_mode": "balanced",
                    "command_intent": "REFRESH_STRATEGY_FRAME",
                    "strategist_invocation": "RUN_REFRESH",
                    "llm_policy": "allow_context_refresh",
                    "strategist_refresh_requested": True,
                    "strategist_refresh_reason": "repeated_hold_monitor_only",
                    "strategist_refresh_context": {
                        "refresh_scope": "open_position_monitor_refresh",
                        "selected_symbol": "322000",
                        "monitor_reason": "too_extended_from_vwap",
                        "refresh_summary": "Repeated hold refresh for 322000 after 3 consecutive hold cycles.",
                        "entry_state": {
                            "current_blocking_axis": "reclaim_readiness",
                            "transition_readiness_score": 0.74,
                            "entry_blockers": ["below_vwap_reclaim_not_ready"],
                        },
                        "prior_monitor_entry_policy_summary": {"volume_ratio_min": 0.68},
                        "current_monitor_entry_policy_summary": {"volume_ratio_min": 0.75},
                    },
                    "open_position_refresh_context": {
                        "refresh_scope": "open_position_monitor_refresh",
                        "selected_symbol": "322000",
                        "monitor_reason": "too_extended_from_vwap",
                        "refresh_summary": "Repeated hold refresh for 322000 after 3 consecutive hold cycles.",
                        "entry_state": {
                            "current_blocking_axis": "reclaim_readiness",
                            "transition_readiness_score": 0.74,
                            "entry_blockers": ["below_vwap_reclaim_not_ready"],
                        },
                    },
                },
            }
        )

    strategist_output = dict(out.get("strategist_output") or {})
    ref = dict(strategist_output.get("commander_context_ref") or {})
    assert ref["strategist_refresh_requested"] is True
    assert ref["strategist_refresh_reason"] == "repeated_hold_monitor_only"
    assert ref["open_position_refresh_context"]["selected_symbol"] == "322000"
    assert ref["open_position_refresh_context"]["entry_state"]["current_blocking_axis"] == "reclaim_readiness"
    assert strategist_output["commander_open_position_refresh_context"]["monitor_reason"] == "too_extended_from_vwap"
    assert strategist_output["selected_symbol_memory"]["symbol"] == "322000"
    assert strategist_output["selected_symbol_memory"]["dominant_monitor_blocker"] == "below_vwap_reclaim_not_ready"
    assert strategist_output["strategic_answers"]["q15_commander_refresh_context"]["selected_symbol"] == "322000"
    assert strategist_output["strategic_answers"]["q15_commander_refresh_context"]["current_monitor_entry_policy_summary"]["volume_ratio_min"] == 0.75
    assert strategist_output["strategic_answers"]["q15_commander_refresh_context"]["selected_symbol_memory"]["symbol"] == "322000"
    assert strategist_output["strategic_answers"]["q15_commander_refresh_context"]["selected_symbol_memory"]["dominant_playbook"] == "pullback"
