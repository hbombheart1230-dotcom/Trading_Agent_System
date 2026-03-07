from __future__ import annotations

from graphs.nodes.decide_trade import decide_trade
from libs.strategies.contracts import StrategyInput
from libs.strategies.v1.config import MeanReversionV1Config, NewsMomentumV1Config
from libs.strategies.v1.mean_reversion_v1 import MeanReversionV1
from libs.strategies.v1.news_momentum_v1 import NewsMomentumV1


def test_mean_reversion_v1_entry_buy_with_oversold_setup():
    strategy = MeanReversionV1(config=MeanReversionV1Config())
    data = StrategyInput(
        symbol="005930",
        regime="range",
        technical={
            "rsi14": 28.0,
            "ma20_gap": -0.03,
            "signal_score": -0.45,
            "volatility20": 0.04,
        },
        news={
            "symbol_sentiment_score": -0.05,
            "global_sentiment_score": 0.00,
            "symbol_sentiment_status": "ok",
            "global_sentiment_status": "ok",
        },
        portfolio={},
        policy={},
    )
    out = strategy.decide(data, price=70000.0, cash=5_000_000.0, held_qty=0).to_dict()
    assert out["action"] == "BUY"
    assert int(out["qty"]) >= 1
    assert out["evidence"]["regime"] == "range"


def test_news_momentum_v1_requires_ok_status_when_enabled():
    strategy = NewsMomentumV1(config=NewsMomentumV1Config(require_ok_status=True))
    data = StrategyInput(
        symbol="005930",
        regime="trend",
        technical={"signal_score": 0.35, "volatility20": 0.05},
        news={
            "symbol_sentiment_score": 0.65,
            "global_sentiment_score": 0.20,
            "symbol_sentiment_status": "fallback",
            "global_sentiment_status": "ok",
        },
        portfolio={},
        policy={},
    )
    out = strategy.decide(data, price=70000.0, cash=5_000_000.0, held_qty=0).to_dict()
    assert out["action"] == "NOOP"
    assert "entry_conditions_not_met" in out["noop_conditions"]


def test_decide_trade_uses_news_momentum_strategy_when_configured():
    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 5_000_000, "open_positions": 0},
        "policy": {
            "use_strategy_v1": True,
            "strategy_v1_name": "news_momentum_v1",
            "use_exit_policy": False,
        },
        "feature_engine": {
            "by_symbol": {
                "005930": {
                    "rsi14": 56.0,
                    "ma20_gap": 0.02,
                    "volatility20": 0.05,
                    "regime": "trend",
                    "signal_score": 0.32,
                }
            }
        },
        "news_sentiment_signal": {
            "005930": {
                "score": 0.72,
                "status": "ok",
                "source": "test",
                "reason": "fixture",
                "ts": 1772812800,
            }
        },
        "global_sentiment_signal": {
            "score": 0.20,
            "status": "ok",
            "source": "test",
            "reason": "fixture",
            "ts": 1772812800,
        },
    }
    out = decide_trade(state)
    assert out["decision_trace"]["strategy"] == "NewsMomentumV1"
    assert out["decision_trace"]["strategy_v1_name"] == "news_momentum_v1"
    assert out["decision_packet"]["intent"]["action"] == "BUY"


def test_decide_trade_auto_strategy_selects_mean_reversion_in_range():
    state = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 5_000_000, "open_positions": 0},
        "policy": {
            "use_strategy_v1": True,
            "strategy_v1_name": "auto",
            "use_exit_policy": False,
        },
        "feature_engine": {
            "by_symbol": {
                "005930": {
                    "rsi14": 30.0,
                    "ma20_gap": -0.02,
                    "volatility20": 0.05,
                    "regime": "range",
                    "signal_score": -0.25,
                }
            }
        },
        "news_sentiment_signal": {
            "005930": {
                "score": 0.05,
                "status": "ok",
                "source": "test",
                "reason": "fixture",
                "ts": 1772812800,
            }
        },
        "global_sentiment_signal": {
            "score": 0.02,
            "status": "ok",
            "source": "test",
            "reason": "fixture",
            "ts": 1772812800,
        },
    }
    out = decide_trade(state)
    assert out["decision_trace"]["strategy"] == "MeanReversionV1"
    assert out["decision_trace"]["strategy_v1_name"] == "mean_reversion_v1"
    assert out["decision_packet"]["intent"]["action"] in ("BUY", "NOOP")
