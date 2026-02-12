from libs.risk.intent import TradeIntent, RiskContext, ExecutionContext, TradeDecisionPacket
from graphs.nodes.execute_from_packet import execute_from_packet


def test_execute_from_packet_mock(tmp_path, monkeypatch):
    # ensure mock executor
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    pkt = TradeDecisionPacket(
        intent=TradeIntent(intent="buy", order_api_id="ORDER_SUBMIT"),
        risk=RiskContext(open_positions=0),
        exec_context=ExecutionContext(values={}),
    )

    # minimal catalog
    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"주문","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "decision_packet": {
            "intent": pkt.intent.to_dict(),
            "risk": pkt.risk.to_dict(),
            "exec_context": pkt.exec_context.to_dict(),
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is True
    assert out["execution"]["payload"]["mode"] == "mock"
