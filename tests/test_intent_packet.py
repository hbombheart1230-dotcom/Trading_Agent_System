from libs.risk.intent import TradeIntent, RiskContext, ExecutionContext, TradeDecisionPacket


def test_packet_to_state():
    pkt = TradeDecisionPacket(
        intent=TradeIntent(intent="buy", order_api_id="ORDER_SUBMIT", symbol="005930", rationale="demo"),
        risk=RiskContext(daily_pnl_ratio=-0.001, per_trade_risk_ratio=0.001, open_positions=0, last_order_epoch=0),
        exec_context=ExecutionContext(values={"qty": 1, "price": 100}),
    )
    st = pkt.to_state("./data/specs/api_catalog.jsonl")
    assert st["order_api_id"] == "ORDER_SUBMIT"
    assert st["intent"] == "buy"
    assert st["context"]["qty"] == 1
    assert st["risk_context"]["open_positions"] == 0
