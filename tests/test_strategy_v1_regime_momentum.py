from __future__ import annotations

from graphs.nodes.decide_trade import decide_trade
from libs.strategies.contracts import StrategyInput
from libs.strategies.v1.config import RegimeMomentumV1Config
from libs.strategies.v1.regime_momentum_v1 import RegimeMomentumV1


def test_regime_momentum_v1_entry_buy_with_sizing():
    strategy = RegimeMomentumV1(config=RegimeMomentumV1Config())
    data = StrategyInput(
        symbol="005930",
        regime="trend",
        technical={"signal_score": 0.6, "ma20_gap": 0.03, "volatility20": 0.02, "rsi14": 57.0},
        news={"symbol_sentiment_score": 0.25, "global_sentiment_score": 0.10},
        portfolio={},
        policy={},
    )
    decision = strategy.decide(data, price=70000.0, cash=5_000_000.0, held_qty=0)
    obj = decision.to_dict()
    assert obj["action"] == "BUY"
    assert int(obj["qty"]) >= 1
    assert float(obj["confidence"]) > 0.0
    assert "evidence" in obj and obj["evidence"]["regime"] == "trend"
    assert "sizing_inputs" in obj
    assert obj["sizing_inputs"]["inputs"]["regime"] == "trend"


def test_regime_momentum_v1_sizing_respects_risk_context():
    strategy = RegimeMomentumV1(config=RegimeMomentumV1Config())
    base = StrategyInput(
        symbol="005930",
        regime="trend",
        technical={"signal_score": 0.7, "ma20_gap": 0.03, "volatility20": 0.03, "rsi14": 58.0},
        news={"symbol_sentiment_score": 0.20, "global_sentiment_score": 0.10},
        portfolio={},
        policy={},
        risk_context={},
    )
    degraded = StrategyInput(
        symbol="005930",
        regime="high_volatility",
        technical={"signal_score": 0.7, "ma20_gap": 0.03, "volatility20": 0.16, "rsi14": 58.0},
        news={"symbol_sentiment_score": 0.20, "global_sentiment_score": 0.10},
        portfolio={"exposure_ratio": 0.8, "daily_pnl_ratio": -0.02},
        policy={"degrade_mode": True},
        risk_context={"correlation_bucket": "high"},
    )
    out_base = strategy.decide(base, price=70000.0, cash=5_000_000.0, held_qty=0).to_dict()
    out_degraded = strategy.decide(degraded, price=70000.0, cash=5_000_000.0, held_qty=0).to_dict()
    assert out_base["action"] == "BUY"
    assert out_degraded["action"] in ("BUY", "NOOP")
    assert int(out_degraded["qty"]) <= int(out_base["qty"])


def test_regime_momentum_v1_exit_sell_when_holding_and_signal_breaks():
    strategy = RegimeMomentumV1(config=RegimeMomentumV1Config())
    data = StrategyInput(
        symbol="005930",
        regime="high_volatility",
        technical={"signal_score": -0.4, "ma20_gap": -0.03, "volatility20": 0.20, "rsi14": 35.0},
        news={"symbol_sentiment_score": -0.20, "global_sentiment_score": -0.10},
        portfolio={},
        policy={},
    )
    decision = strategy.decide(data, price=68000.0, cash=1_000_000.0, held_qty=16)
    obj = decision.to_dict()
    assert obj["action"] == "SELL"
    assert int(obj["qty"]) == 16
    assert bool(obj["invalidation"]["triggered"]) is True


def test_decide_trade_uses_strategy_v1_when_enabled(monkeypatch):
    monkeypatch.setenv("USE_STRATEGY_V1", "true")
    monkeypatch.setenv("USE_EXIT_POLICY", "false")

    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 5_000_000, "open_positions": 0},
        "feature_engine": {
            "by_symbol": {
                "005930": {
                    "rsi14": 58.0,
                    "ma20_gap": 0.02,
                    "atr14": 550.0,
                    "volume_spike20": 1.2,
                    "volatility20": 0.03,
                    "regime": "trend",
                    "signal_score": 0.7,
                }
            }
        },
        "news_sentiment": {"005930": 0.30},
        "global_sentiment": {"score": 0.10},
    }
    out = decide_trade(state)
    assert out["decision_trace"]["strategy"] == "RegimeMomentumV1"
    assert out["decision_packet"]["intent"]["action"] == "BUY"
    assert "strategy_v1_decision" in out["decision_trace"]
    assert "why" in out["decision_packet"]
    assert "invalidation" in out["decision_packet"]
    assert "sizing_inputs" in out["decision_packet"]
    assert out["decision_packet"]["why"]["regime"] == "trend"
