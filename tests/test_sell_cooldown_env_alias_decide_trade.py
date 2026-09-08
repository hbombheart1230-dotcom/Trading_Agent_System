from __future__ import annotations

import time

from graphs.nodes.decide_trade import decide_trade


def test_sell_cooldown_env_alias_blocks_fast_sell(monkeypatch):
    monkeypatch.setenv("USE_EXIT_POLICY", "true")
    monkeypatch.setenv("EXIT_POLICY_MAX_HOLD_SEC", "1")
    monkeypatch.setenv("MIN_HOLD_SECONDS", "0")
    monkeypatch.setenv("SELL_COOLDOWN", "900")
    monkeypatch.delenv("SELL_COOLDOWN_SEC", raising=False)
    monkeypatch.setattr(time, "time", lambda: 2000.0)

    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {
            "cash": 2_000_000,
            "positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0}],
            "open_positions": 1,
        },
        "persisted_state": {"last_trade_side": "BUY", "last_trade_epoch": 1950},
        "risk_context": {"open_positions": 1, "daily_pnl_ratio": 0.0, "last_order_epoch": 0},
    }

    out = decide_trade(state)
    intent = out["decision_packet"]["intent"]
    assert intent["action"] == "NOOP"
    assert intent["reason"] == "sell_guard_min_hold"
    assert "sell_guard_min_hold" in str(intent.get("rationale") or "")
