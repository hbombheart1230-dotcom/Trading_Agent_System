from __future__ import annotations

from graphs.nodes.monitor_node import monitor_node
from graphs.nodes.scanner_node import scanner_node
from graphs.nodes.strategist_node import strategist_node


def test_m31_17_strategist_outputs_themes_and_candidates_contract(monkeypatch):
    monkeypatch.setenv("TOP_N_CANDIDATES", "4")
    state = {
        "themes": ["semiconductor", "AI"],
        "candidate_symbols": ["005930", "000660", "042700", "058470", "091990"],
        "policy": {
            "use_global_sentiment": False,
            "use_news_analysis": False,
            "use_universe_builder": False,
        },
    }

    out = strategist_node(state)

    strategist_output = out.get("strategist_output") or {}
    assert strategist_output["themes"] == ["semiconductor", "AI"]
    assert strategist_output["candidates"] == ["005930", "000660", "042700", "058470"]
    assert int(strategist_output["candidate_count"]) == 4
    assert out.get("themes") == ["semiconductor", "AI"]
    for key in (
        "market_regime",
        "market_sentiment",
        "key_events",
        "avoid_themes",
        "playbook",
        "scanner_bias",
        "scanner_priority",
        "trade_aggressiveness",
        "risk_tone",
        "monitor_guidance",
        "report_focus",
        "strategic_answers",
    ):
        assert key in strategist_output
    assert strategist_output["market_regime"] in ("risk_on", "neutral", "risk_off")
    assert strategist_output["market_sentiment"] in ("bullish", "neutral", "bearish")
    assert strategist_output["playbook"] in ("breakout", "pullback", "reversal", "defensive")
    assert strategist_output["scanner_bias"] in ("large_cap", "leader", "momentum", "value")
    assert strategist_output["risk_tone"] in ("conservative", "normal", "aggressive")
    assert strategist_output["monitor_guidance"] in ("hold_through_noise", "defensive_exit", "quick_take_profit")
    assert strategist_output["trade_aggressiveness"] in ("low", "medium", "high")
    assert isinstance(strategist_output["scanner_priority"], list)
    assert isinstance(strategist_output.get("monitor_policy"), dict)
    assert isinstance(strategist_output["report_focus"], list)
    assert isinstance(strategist_output["strategic_answers"], dict)


def test_m31_17_scanner_accepts_strategist_output_and_emits_top_stock():
    state = {
        "strategist_output": {
            "themes": ["semiconductor"],
            "avoid_themes": ["high_gap_speculative"],
            "candidates": ["005930", "000660"],
            "scanner_bias": "momentum",
            "scanner_priority": ["momentum", "trend_strength", "liquidity"],
            "trade_aggressiveness": "high",
            "risk_tone": "aggressive",
        },
        "mock_scan_results": {
            "005930": {"score": 0.91, "risk_score": 0.20, "confidence": 0.88},
            "000660": {"score": 0.75, "risk_score": 0.21, "confidence": 0.84},
        },
    }

    out = scanner_node(state)
    assert (out.get("selected") or {}).get("symbol") == "005930"
    assert out.get("top_stock") == "005930"
    scanner_output = out.get("scanner_output") or {}
    assert scanner_output.get("top_stock") == "005930"
    assert float(scanner_output.get("score") or 0.0) == 0.91
    assert scanner_output.get("strategist_scanner_priority") == ["momentum", "trend_strength", "liquidity"]
    assert scanner_output.get("strategist_scanner_bias") == "momentum"
    assert scanner_output.get("strategist_trade_aggressiveness") == "high"
    assert scanner_output.get("strategist_risk_tone") == "aggressive"


def test_m31_17_monitor_sell_cooldown_env_alias_is_supported(monkeypatch):
    monkeypatch.delenv("SELL_COOLDOWN_SEC", raising=False)
    monkeypatch.setenv("SELL_COOLDOWN", "900")
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("MONITOR_EXIT_CONFIRM_TICKS", "1")

    state = {
        "plan": {"thesis": "demo"},
        "selected": {
            "symbol": "005930",
            "score": 0.9,
            "risk_score": 0.2,
            "confidence": 0.8,
        },
        "portfolio_snapshot": {
            "positions": [{"symbol": "005930", "qty": 3, "avg_price": 70000.0, "hold_sec": 120}]
        },
        "market_snapshot": {"symbol": "005930", "price": 68000.0},
        "policy": {
            "use_exit_policy": True,
            "stop_loss_pct": 0.01,
            "take_profit_pct": 0.20,
        },
    }

    out1 = monitor_node(state)
    intents1 = out1.get("intents") or []
    assert len(intents1) == 1
    assert intents1[0]["side"] == "SELL"

    out2 = monitor_node(out1)
    assert out2.get("intents") == []
    exit_info = out2.get("monitor_exit") or {}
    assert bool(exit_info.get("sell_guard_blocked")) is True
    reason = str(exit_info.get("sell_guard_reason") or "")
    assert ("sell_guard_pending_exit_lock" in reason) or ("sell_guard_cooldown" in reason)
