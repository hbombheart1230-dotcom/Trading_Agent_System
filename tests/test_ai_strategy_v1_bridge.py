from __future__ import annotations

from libs.ai.strategist import StrategyInput, StrategyV1Strategist


def _base_snapshot() -> dict:
    return {
        "symbol": "005930",
        "price": 70000.0,
        "llm_context": {
            "technical": {
                "regime": "trend",
                "signal_score": 0.35,
                "ma20_gap": 0.02,
                "volatility20": 0.05,
                "rsi14": 58.0,
            },
            "news": {
                "symbol_sentiment_score": 0.65,
                "global_sentiment_score": 0.10,
                "symbol_sentiment_status": "ok",
                "global_sentiment_status": "ok",
            },
        },
    }


def test_strategy_v1_strategist_bridges_to_news_momentum_buy():
    strategist = StrategyV1Strategist(policy={"strategy_v1_name": "news_momentum_v1"})
    x = StrategyInput(
        symbol="005930",
        market_snapshot=_base_snapshot(),
        portfolio_snapshot={"cash": 5_000_000.0, "positions": []},
        risk_context={},
    )
    d = strategist.decide(x)
    assert d.intent["action"] == "BUY"
    assert d.intent["symbol"] == "005930"
    assert int(d.intent["qty"]) >= 1
    assert d.meta["strategy_v1_name"] == "news_momentum_v1"
    assert isinstance(d.meta.get("evidence"), dict)


def test_strategy_v1_strategist_bridges_to_exit_when_holding():
    strategist = StrategyV1Strategist(policy={"strategy_v1_name": "news_momentum_v1"})
    snap = _base_snapshot()
    snap["llm_context"]["news"]["symbol_sentiment_score"] = -0.5
    x = StrategyInput(
        symbol="005930",
        market_snapshot=snap,
        portfolio_snapshot={"cash": 100_000.0, "positions": [{"symbol": "005930", "qty": 3}]},
        risk_context={},
    )
    d = strategist.decide(x)
    assert d.intent["action"] == "SELL"
    assert int(d.intent["qty"]) == 3
    assert d.meta["strategy_v1_name"] == "news_momentum_v1"

