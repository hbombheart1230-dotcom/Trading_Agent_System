from libs.ai.strategist import RuleStrategist
from graphs.nodes.decide_trade import decide_trade

def test_decide_trade_uses_injected_strategist():
    st = {
        "symbol": "005930",
        "market_snapshot": {"symbol": "005930", "price": 70000},
        "portfolio_snapshot": {"cash": 10_000_000, "open_positions": 0},
        "strategist": RuleStrategist(),
    }
    out = decide_trade(st)
    pkt = out["decision_packet"]
    assert pkt["intent"]["action"] in ("BUY", "NOOP")
    assert "risk" in pkt and "exec_context" in pkt
