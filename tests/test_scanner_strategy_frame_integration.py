from __future__ import annotations

from datetime import datetime, timedelta, timezone

from graphs.nodes.scanner_node import _apply_scanner_guidance_weights, _extract_scanner_guidance, scanner_node


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


def test_scanner_repeat_guard_penalizes_recently_selected_symbol():
    now_epoch = 1_800_000_000
    state = {
        "now_epoch": now_epoch,
        "candidates": [
            {"symbol": "AAA", "sources": ["top_value"], "source_scores": {"top_value": 2.0}},
            {"symbol": "BBB", "sources": ["top_value"], "source_scores": {"top_value": 1.0}},
        ],
        "mock_scan_results": {
            "AAA": {"score": 0.50, "risk_score": 0.20, "confidence": 0.80},
            "BBB": {"score": 0.50, "risk_score": 0.20, "confidence": 0.80},
        },
        "persisted_state": {
            "recent_scanner_selected": [
                {"symbol": "AAA", "epoch": now_epoch - 60},
                {"symbol": "AAA", "epoch": now_epoch - 120},
                {"symbol": "AAA", "epoch": now_epoch - 180},
                {"symbol": "AAA", "epoch": now_epoch - 240},
            ],
            "last_trade_symbol": "AAA",
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
    assert (out.get("selected") or {}).get("symbol") == "BBB"
    rows = {str(r.get("symbol")): r for r in out.get("scan_results", []) if isinstance(r, dict)}
    assert float((rows["AAA"].get("score_breakdown") or {}).get("repeat_symbol_penalty") or 0.0) < 0.0
    assert bool(((rows["AAA"].get("components") or {}).get("recent_trade_same_symbol"))) is True
    assert str(((out.get("persisted_state") or {}).get("recent_scanner_selected") or [])[-1].get("symbol")) == "BBB"
