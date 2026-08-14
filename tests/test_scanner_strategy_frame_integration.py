from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from graphs.nodes.scanner_node import (
    _apply_scanner_guidance_weights,
    _candidate_quote_metrics,
    _compute_symbol_prior_adjustment,
    _extract_scanner_guidance,
    scanner_node,
)


def _neutral_scanner_features(*symbols: str) -> dict[str, dict[str, float]]:
    return {
        symbol: {
            "return20": 0.0,
            "ma20_gap": 0.0,
            "ma60_gap": 0.0,
            "ma120_gap": 0.0,
            "trend_strength": 0.0,
            "adx14": 0.0,
            "volume_spike20": 1.0,
            "vwap_distance": 0.0,
            "cross_section_rank": 0.0,
            "volatility20": 0.0,
            "signal_score": 0.0,
        }
        for symbol in symbols
    }


def _flat_candidate_metrics(*symbols: str) -> dict[str, dict[str, float]]:
    return {
        symbol: {"change_pct": 0.0, "volume": 1.0, "trading_value": 1.0}
        for symbol in symbols
    }


class _FakeSkillRunnerQuotes:
    def run(self, *, run_id: str, skill: str, args: dict) -> dict:
        symbol = str(args.get("symbol") or "")
        if skill == "market.quote":
            price_map = {"005930": 70500, "000660": 128000}
            price = int(price_map.get(symbol, 1000))
            return {
                "result": {
                    "action": "ready",
                    "data": {
                        "symbol": symbol,
                        "cur": price,
                        "best_bid": price,
                        "best_ask": price + 50,
                        "raw": {
                            "cntr_infr": [
                                {
                                    "cur_prc": f"+{price}",
                                    "pri_sel_bid_unit": f"+{price + 50}",
                                    "pri_buy_bid_unit": f"+{price}",
                                    "acc_trde_qty": "1234567",
                                    "acc_trde_prica": "89012345678",
                                    "pre_rt": "+2.15",
                                }
                            ]
                        },
                    },
                }
            }
        if skill == "account.orders":
            return {
                "result": {
                    "action": "ready",
                    "data": {"rows": [{"symbol": "005930", "order_id": "ord-1"}]},
                }
            }
        return {"result": {"action": "error", "meta": {"error_type": "unsupported_skill"}}}


def test_scanner_playbook_additively_changes_weights():
    base = {
        "trading_value": 0.20,
        "momentum": 0.22,
        "trend": 0.20,
        "volume_surge": 0.14,
        "intraday_strength": 0.12,
        "theme_boost": 0.06,
        "sentiment": 0.06,
        "volatility_penalty": 0.10,
        "gap_penalty": 0.07,
        "open_order_penalty": 0.04,
    }
    breakout = _apply_scanner_guidance_weights(
        dict(base),
        playbook="breakout",
        scanner_bias="momentum",
        scanner_priority=["momentum", "trend_strength"],
        trade_aggressiveness="high",
        risk_tone="aggressive",
    )
    defensive = _apply_scanner_guidance_weights(
        dict(base),
        playbook="defensive",
        scanner_bias="large_cap",
        scanner_priority=["liquidity", "risk_penalty"],
        trade_aggressiveness="low",
        risk_tone="conservative",
    )

    assert breakout["momentum"] > defensive["momentum"]
    assert defensive["volatility_penalty"] > breakout["volatility_penalty"]
    assert defensive["trading_value"] >= base["trading_value"]


def test_scanner_extract_guidance_reads_strategist_output_contract():
    state = {
        "strategist_output": {
            "themes": ["semiconductor", "ai"],
            "avoid_themes": ["biotech_smallcap"],
            "playbook": "breakout",
            "scanner_bias": "momentum",
            "scanner_priority": ["momentum", "trend_strength"],
            "scanner_source_policy": {
                "include_change_rate": True,
                "preferred_sources": ["top_change_rate", "condition_search"],
            },
            "trade_aggressiveness": "high",
            "risk_tone": "aggressive",
        }
    }
    out = _extract_scanner_guidance(state)

    assert out["themes"] == ["semiconductor", "ai"]
    assert out["avoid_themes"] == ["biotech_smallcap"]
    assert out["playbook"] == "breakout"
    assert out["scanner_bias"] == "momentum"
    assert out["scanner_priority"] == ["momentum", "trend_strength"]
    assert out["scanner_source_policy"]["include_change_rate"] is True
    assert out["scanner_source_policy"]["preferred_sources"] == ["top_change_rate", "condition_search"]
    assert out["trade_aggressiveness"] == "high"
    assert out["risk_tone"] == "aggressive"


def test_candidate_quote_metrics_include_spread_bps_from_quote_snapshot():
    metrics = _candidate_quote_metrics(
        "005930",
        skill_quotes={
            "005930": {
                "price": 70500,
                "best_bid": 70500,
                "best_ask": 70550,
                "raw": {
                    "cntr_infr": [
                        {
                            "acc_trde_qty": "1234567",
                            "acc_trde_prica": "89012345678",
                            "pre_rt": "+2.15",
                        }
                    ]
                },
            }
        },
        state={},
    )

    assert metrics["best_bid"] == 70500.0
    assert metrics["best_ask"] == 70550.0
    assert float(metrics["spread_bps"]) > 0.0


def test_scanner_extract_guidance_prefers_strategy_policy_when_present():
    state = {
        "strategist_output": {
            "themes": ["semiconductor"],
            "avoid_themes": ["high_gap_speculative"],
            "playbook": "defensive",
            "scanner_priority": ["trading_value"],
            "scanner_source_policy": {"include_change_rate": True},
            "trade_aggressiveness": "low",
            "risk_tone": "conservative",
            "strategy_policy": {
                "scanner_policy": {
                    "candidate_sources": {
                        "include_change_rate": False,
                        "preferred_sources": ["top_value", "top_volume"],
                    },
                    "priority_tilts": ["trend_strength", "volume_surge"],
                    "score_weights": {"momentum": 0.05, "trend": 0.30},
                }
            },
        }
    }

    out = _extract_scanner_guidance(state)
    assert out["scanner_priority"] == ["trend_strength", "volume_surge"]
    assert out["scanner_source_policy"]["include_change_rate"] is False
    assert out["scanner_source_policy"]["preferred_sources"] == ["top_value", "top_volume"]
    assert float((out.get("score_weights") or {}).get("trend") or 0.0) == 0.30


def test_scanner_extract_guidance_includes_commander_context_and_strategist_plan():
    state = {
        "strategist_output": {
            "playbook": "breakout",
            "strategy_policy": {
                "scanner_policy": {
                    "priority_tilts": ["trend_strength", "volume_surge"],
                },
                "commander_context": {
                    "scanner_mission": "Prioritize liquid leaders.",
                    "allowed_playbooks": ["breakout", "pullback"],
                    "banned_playbooks": ["reversal"],
                    "risk_mode": "balanced",
                    "command_intent": "OBSERVE_ONLY",
                    "strategist_invocation": "RUN",
                    "no_trade_reason_code": "WAIT_FOR_CONFIRMATION",
                    "source_priority": ["shadow_commander", "runtime_observation", "strategist_fallback"],
                    "shadow_used": True,
                    "strategist_fallback_used": False,
                },
                "strategist_plan": {
                    "selected_playbook": "breakout",
                    "candidate_hypotheses": ["liquid_semiconductor_leaders"],
                    "symbol_constraints": {"scanner_priority": ["liquidity", "momentum"]},
                    "strategy_summary": "Prefer liquid leaders with momentum confirmation.",
                },
                "provenance": {
                    "shadow_used": True,
                    "strategist_fallback_used": False,
                },
            },
        }
    }

    out = _extract_scanner_guidance(state)
    assert out["commander_context"]["scanner_mission"] == "Prioritize liquid leaders."
    assert out["commander_context"]["allowed_playbooks"] == ["breakout", "pullback"]
    assert out["strategist_plan"]["selected_playbook"] == "breakout"
    assert out["policy_provenance"]["shadow_used"] is True
    assert out["scanner_priority"] == ["trend_strength", "volume_surge"]


def test_scanner_output_records_commander_context_consumption():
    state = {
        "strategist_output": {
            "themes": ["semiconductor"],
            "playbook": "breakout",
            "candidates": ["005930", "000660"],
            "scanner_bias": "momentum",
            "scanner_priority": ["momentum", "trend_strength", "liquidity"],
            "trade_aggressiveness": "high",
            "risk_tone": "aggressive",
            "strategy_policy": {
                "scanner_policy": {},
                "commander_context": {
                    "scanner_mission": "Prioritize liquid leaders.",
                    "allowed_playbooks": ["breakout"],
                    "risk_mode": "balanced",
                    "command_intent": "OBSERVE_ONLY",
                    "strategist_invocation": "RUN",
                    "no_trade_reason_code": "WAIT_FOR_CONFIRMATION",
                    "source_priority": ["shadow_commander", "runtime_observation", "strategist_fallback"],
                    "shadow_used": True,
                    "strategist_fallback_used": False,
                },
                "strategist_plan": {
                    "selected_playbook": "breakout",
                    "candidate_hypotheses": ["liquid_semiconductor_leaders"],
                    "symbol_constraints": {"max_gap_pct": 0.03},
                    "strategy_summary": "Prefer liquid leaders with momentum confirmation.",
                },
                "provenance": {
                    "shadow_used": True,
                    "strategist_fallback_used": False,
                },
            },
        },
        "mock_scan_results": {
            "005930": {"score": 0.91, "risk_score": 0.20, "confidence": 0.88},
            "000660": {"score": 0.75, "risk_score": 0.21, "confidence": 0.84},
        },
    }

    out = scanner_node(state)
    scanner_output = out.get("scanner_output") or {}
    selection_reason = out.get("scanner_candidate_selection_reason") or {}
    selected = out.get("selected") or {}

    assert selected.get("symbol") == "005930"
    assert scanner_output.get("commander_context_consumed") is True
    assert "scanner_mission" in list(scanner_output.get("consumed_fields") or [])
    assert scanner_output.get("commander_priority_ref", {}).get("risk_mode") == "balanced"
    assert scanner_output.get("strategist_constraints_ref", {}).get("selected_playbook") == "breakout"
    assert scanner_output.get("selection_basis", {}).get("commander_context_consumed") is True
    assert scanner_output.get("shadow_used") is True
    assert scanner_output.get("strategist_fallback_used") is False
    assert selection_reason.get("selection_basis", {}).get("strategist_plan_consumed") is True
    assert selection_reason.get("strategist_constraints_ref", {}).get("selected_playbook") == "breakout"
    assert (selected.get("tactic_suitability") or {}).get("behavior_effect") == "observation_only"
    assert (scanner_output.get("tactic_suitability") or {}).get("schema_version") == "tactic_suitability.v1"
    assert (out.get("scanner_ranking_table") or [{}])[0].get("tactic_suitability", {}).get("schema_version") == "tactic_suitability.v1"
    assert (selection_reason.get("tactic_suitability") or {}).get("schema_version") == "tactic_suitability.v1"


def test_scanner_applies_symbol_prior_deterministically():
    state = {
        "candidates": [
            {"symbol": "005930", "sources": ["top_value"], "source_scores": {"top_value": 1.0}},
            {"symbol": "000660", "sources": ["top_value"], "source_scores": {"top_value": 1.0}},
        ],
        "mock_scan_results": {
            "005930": {"score": 0.80, "risk_score": 0.20, "confidence": 0.80},
            "000660": {"score": 0.80, "risk_score": 0.20, "confidence": 0.80},
        },
        "strategist_output": {
            "playbook": "breakout",
            "scanner_priority": ["momentum", "trend_strength"],
            "trade_aggressiveness": "medium",
            "risk_tone": "normal",
        },
    }

    def _fake_symbol_read_model(_trades_root: str, symbol: str, persisted_only: bool = False) -> dict:
        if symbol == "005930":
            return {
                "symbol": "005930",
                "avg_pnl_pct": -0.7,
                "win_rate": 0.20,
                "dominant_playbook": "pullback",
                "dominant_monitor_blocker": "confirmed_entry",
                "repeated_failure_pattern": [{"type": "entry_pattern", "value": "breakout", "count": 3}],
                "data_quality": {"data_source": "symbol_memory"},
            }
        return {
            "symbol": "000660",
            "avg_pnl_pct": 0.4,
            "win_rate": 0.70,
            "dominant_playbook": "breakout",
            "dominant_monitor_blocker": "unknown",
            "repeated_failure_pattern": [],
            "data_quality": {"data_source": "symbol_memory"},
        }

    with patch("graphs.nodes.scanner_node.build_symbol_read_model", side_effect=_fake_symbol_read_model):
        out = scanner_node(state)

    selected = out.get("selected") or {}
    scanner_output = out.get("scanner_output") or {}
    ranked = list(out.get("ranked_candidates") or [])

    assert selected.get("symbol") == "000660"
    assert ranked[0]["symbol"] == "000660"
    assert ranked[1]["symbol"] == "005930"
    assert scanner_output["candidate_symbol_prior_adjustments"][0]["symbol"] == "000660"
    assert any("playbook_fit:breakout" in reason for reason in scanner_output["candidate_symbol_prior_adjustments"][0]["symbol_prior_reasons"])
    losing_prior = [row for row in scanner_output["candidate_symbol_prior_adjustments"] if row["symbol"] == "005930"][0]
    assert losing_prior["symbol_prior_adjustment"] < 0.0
    assert any("playbook_mismatch:pullback" in reason for reason in losing_prior["symbol_prior_reasons"])


def test_scanner_uses_chart_features_when_available():
    state = {
        "candidates": [
            {"symbol": "AAA", "sources": ["top_value"], "source_scores": {"top_value": 1.0}},
            {"symbol": "BBB", "sources": ["top_value"], "source_scores": {"top_value": 1.0}},
        ],
        "mock_scan_results": {
            "AAA": {"score": 0.50, "risk_score": 0.20, "confidence": 0.80},
            "BBB": {"score": 0.50, "risk_score": 0.20, "confidence": 0.80},
        },
        "strategist_output": {
            "playbook": "breakout",
            "scanner_bias": "momentum",
            "scanner_priority": ["momentum", "trend_strength", "ma_alignment", "vwap_reclaim", "cross_section_rank"],
            "trade_aggressiveness": "high",
            "risk_tone": "aggressive",
        },
        "scanner_features": {
            "AAA": {
                "return20": 0.12,
                "ma20_gap": 0.04,
                "ma60_gap": 0.06,
                "ma120_gap": 0.08,
                "trend_strength": 0.85,
                "adx14": 31.0,
                "volume_spike20": 2.4,
                "vwap_distance": 0.015,
                "cross_section_rank": 1.0,
                "volatility20": 0.02,
            },
            "BBB": {
                "return20": -0.02,
                "ma20_gap": -0.01,
                "ma60_gap": -0.02,
                "ma120_gap": -0.03,
                "trend_strength": -0.20,
                "adx14": 12.0,
                "volume_spike20": 1.0,
                "vwap_distance": -0.010,
                "cross_section_rank": 0.1,
                "volatility20": 0.02,
            },
        },
        "policy": {
            "enable_practical_scoring": True,
            "weight_news": 0.0,
            "weight_global": 0.0,
            "risk_news_penalty": 0.0,
            "risk_global_penalty": 0.0,
            "confidence_news_boost": 0.0,
        },
    }

    out = scanner_node(state)
    assert (out.get("selected") or {}).get("symbol") == "AAA"
    rows = {str(r.get("symbol")): r for r in out.get("scan_results", []) if isinstance(r, dict)}
    assert float((rows["AAA"].get("score_breakdown") or {}).get("ma_alignment") or 0.0) > 0.0
    assert float((rows["AAA"].get("score_breakdown") or {}).get("vwap_alignment") or 0.0) > 0.0
    assert float((rows["AAA"].get("score_breakdown") or {}).get("cross_section_rank") or 0.0) > 0.0
    assert float(rows["AAA"].get("scanner_macro_chart_fit_score") or 0.0) > 0.5
    assert float((rows["AAA"].get("score_breakdown") or {}).get("scanner_macro_chart_fit_bias") or 0.0) > 0.0
    assert rows["AAA"].get("scanner_macro_chart_fit_authority") == "soft_rank_bias_only"
    assert (out.get("scanner_output") or {}).get("scanner_macro_chart_fit_score") == rows["AAA"].get(
        "scanner_macro_chart_fit_score"
    )


def _seed_rows(*, start_price: float, drift: float, rows: int = 80) -> list[dict]:
    base_ts = datetime(2026, 3, 16, tzinfo=timezone.utc)
    out = []
    price = float(start_price)
    for idx in range(rows):
        ts = int((base_ts + timedelta(days=idx)).timestamp())
        open_p = price
        close = max(1.0, price * (1.0 + drift))
        high = max(open_p, close) * 1.01
        low = min(open_p, close) * 0.99
        out.append(
            {
                "ts": ts,
                "open": round(open_p, 4),
                "high": round(high, 4),
                "low": round(low, 4),
                "close": round(close, 4),
                "volume": float(1000 + (idx * 5)),
            }
        )
        price = close
    return out


def test_scanner_hydrates_candidate_features_from_seed_rows_when_feature_map_missing():
    state = {
        "candidates": [
            {"symbol": "AAA", "sources": ["top_value"], "source_scores": {"top_value": 1.0}},
            {"symbol": "BBB", "sources": ["top_value"], "source_scores": {"top_value": 1.0}},
        ],
        "mock_scan_results": {
            "AAA": {"score": 0.50, "risk_score": 0.20, "confidence": 0.80},
            "BBB": {"score": 0.50, "risk_score": 0.20, "confidence": 0.80},
        },
        "strategist_output": {
            "playbook": "breakout",
            "scanner_bias": "momentum",
            "scanner_priority": ["momentum", "trend_strength", "ma_alignment", "vwap_distance", "cross_section_rank"],
            "trade_aggressiveness": "high",
            "risk_tone": "aggressive",
        },
        "scanner_feature_seed_rows": {
            "AAA": _seed_rows(start_price=100.0, drift=0.01),
            "BBB": _seed_rows(start_price=100.0, drift=-0.005),
        },
        "policy": {
            "enable_practical_scoring": True,
            "weight_news": 0.0,
            "weight_global": 0.0,
            "risk_news_penalty": 0.0,
            "risk_global_penalty": 0.0,
            "confidence_news_boost": 0.0,
            "scanner_feature_seed_with_yf": False,
        },
    }

    out = scanner_node(state)
    assert (out.get("selected") or {}).get("symbol") == "AAA"
    assert ((out.get("selected") or {}).get("features") or {}).get("engine_ma20_gap") is not None
    assert ((out.get("selected") or {}).get("features") or {}).get("engine_adx14") is not None
    assert ((out.get("selected") or {}).get("features") or {}).get("engine_cross_section_rank") is not None
    assert str((out.get("scanner_feature") or {}).get("source") or "").startswith("scanner_candidate_hydration")


def test_scanner_auto_hydrates_skill_quotes_for_live_symbols():
    state = {
        "run_id": "r-skill-auto",
        "skill_runner": _FakeSkillRunnerQuotes(),
        "candidates": [
            {"symbol": "005930", "sources": ["top_value"], "source_scores": {"top_value": 1.0}},
            {"symbol": "000660", "sources": ["top_value"], "source_scores": {"top_value": 1.0}},
        ],
        "mock_scan_results": {
            "005930": {"score": 0.50, "risk_score": 0.20, "confidence": 0.80},
            "000660": {"score": 0.50, "risk_score": 0.20, "confidence": 0.80},
        },
        "policy": {
            "enable_practical_scoring": True,
            "weight_news": 0.0,
            "weight_global": 0.0,
            "risk_news_penalty": 0.0,
            "risk_global_penalty": 0.0,
            "confidence_news_boost": 0.0,
            "scanner_feature_seed_with_yf": False,
            "enable_scanner_skill_hydration": True,
        },
    }

    out = scanner_node(state)

    rows = {str(r.get("symbol")): r for r in out.get("scan_results", []) if isinstance(r, dict)}
    assert out["scanner_skill"]["used"] is True
    assert out["scanner_skill"]["quote_symbols"] == 2
    assert out["scanner_skill"]["account_order_rows"] == 1
    assert rows["005930"]["features"]["skill_quote_price"] == 70500.0
    assert rows["005930"]["features"]["quote_volume"] > 0.0
    assert rows["005930"]["features"]["quote_trading_value"] > 0.0


def test_scanner_repeat_guard_penalizes_recently_selected_symbol(tmp_path):
    now_epoch = 1_800_000_000
    state = {
        "now_epoch": now_epoch,
        "candidates": [
            {"symbol": "005930", "sources": ["top_value"], "source_scores": {"top_value": 2.0}},
            {"symbol": "000660", "sources": ["top_value"], "source_scores": {"top_value": 1.0}},
        ],
        "mock_scan_results": {
            "005930": {"score": 0.50, "risk_score": 0.20, "confidence": 0.80},
            "000660": {"score": 0.50, "risk_score": 0.20, "confidence": 0.80},
        },
        "scanner_features": _neutral_scanner_features("005930", "000660"),
        "mock_candidate_metrics": _flat_candidate_metrics("005930", "000660"),
        "reports_root": str(tmp_path / "reports"),
        "persisted_state": {
            "recent_scanner_selected": [
                {"symbol": "005930", "epoch": now_epoch - 60},
                {"symbol": "005930", "epoch": now_epoch - 120},
                {"symbol": "005930", "epoch": now_epoch - 180},
                {"symbol": "005930", "epoch": now_epoch - 240},
            ],
            "last_trade_symbol": "005930",
            "last_trade_epoch": now_epoch - 300,
        },
        "policy": {
            "enable_practical_scoring": True,
            "weight_news": 0.0,
            "weight_global": 0.0,
            "risk_news_penalty": 0.0,
            "risk_global_penalty": 0.0,
            "confidence_news_boost": 0.0,
            "scanner_repeat_guard": {
                "lookback_sec": 1800,
                "per_hit_penalty": 0.06,
                "recent_trade_penalty": 0.10,
                "trade_lookback_sec": 3600,
                "max_penalty": 0.24,
            },
        },
    }

    out = scanner_node(state)
    assert (out.get("selected") or {}).get("symbol") == "000660"
    rows = {str(r.get("symbol")): r for r in out.get("scan_results", []) if isinstance(r, dict)}
    assert float((rows["005930"].get("score_breakdown") or {}).get("repeat_symbol_penalty") or 0.0) < 0.0
    assert bool(((rows["005930"].get("components") or {}).get("recent_trade_same_symbol"))) is True
    assert str(((out.get("persisted_state") or {}).get("recent_scanner_selected") or [])[-1].get("symbol")) == "000660"


def test_scanner_repeat_guard_penalizes_recently_blocked_symbol_with_same_reason(tmp_path):
    now_epoch = 1_800_000_000
    state = {
        "now_epoch": now_epoch,
        "candidates": [
            {"symbol": "005930", "sources": ["top_value"], "source_scores": {"top_value": 2.0}},
            {"symbol": "000660", "sources": ["top_value"], "source_scores": {"top_value": 1.0}},
        ],
        "mock_scan_results": {
            "005930": {"score": 0.50, "risk_score": 0.20, "confidence": 0.80},
            "000660": {"score": 0.50, "risk_score": 0.20, "confidence": 0.80},
        },
        "scanner_features": _neutral_scanner_features("005930", "000660"),
        "mock_candidate_metrics": _flat_candidate_metrics("005930", "000660"),
        "reports_root": str(tmp_path / "reports"),
        "persisted_state": {
            "recent_monitor_blocks": [
                {"symbol": "005930", "reason": "too_extended_from_vwap", "epoch": now_epoch - 60},
                {"symbol": "005930", "reason": "too_extended_from_vwap", "epoch": now_epoch - 120},
                {"symbol": "005930", "reason": "too_extended_from_vwap", "epoch": now_epoch - 180},
            ],
        },
        "policy": {
            "enable_practical_scoring": True,
            "weight_news": 0.0,
            "weight_global": 0.0,
            "risk_news_penalty": 0.0,
            "risk_global_penalty": 0.0,
            "confidence_news_boost": 0.0,
            "scanner_repeat_guard": {
                "blocker_lookback_sec": 900,
                "blocker_per_hit_penalty": 0.08,
                "blocker_max_penalty": 0.18,
            },
        },
    }

    out = scanner_node(state)
    assert (out.get("selected") or {}).get("symbol") == "000660"
    rows = {str(r.get("symbol")): r for r in out.get("scan_results", []) if isinstance(r, dict)}
    assert float((rows["005930"].get("score_breakdown") or {}).get("repeat_blocker_penalty") or 0.0) < 0.0
    assert str((rows["005930"].get("components") or {}).get("recent_blocker_reason") or "") == "too_extended_from_vwap"


def test_scanner_symbol_prior_strongly_penalizes_same_day_repeat_loser():
    result = _compute_symbol_prior_adjustment(
        symbol_model={
            "last_trade_date": "2026-05-12",
            "closed_trade_count": 5,
            "loss_count": 3,
            "win_rate": 0.4,
            "avg_pnl_pct": -0.18,
            "dominant_playbook": "pullback",
            "dominant_monitor_blocker": "vwap_breakdown",
        },
        playbook="pullback",
        current_day="2026-05-12",
    )

    assert result["adjustment"] <= -0.40
    assert result["risk_delta"] >= 0.30
    assert result["confidence_delta"] <= -0.20
    assert "same_day_trade_lockout_bias" in result["reasons"]
