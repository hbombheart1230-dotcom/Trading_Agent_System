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


def test_execute_from_packet_uses_real_mode_when_execution_mode_unset(tmp_path, monkeypatch):
    # EXECUTION_MODE unset, but KIWOOM_MODE=real => must not bypass supervisor.
    monkeypatch.delenv("EXECUTION_MODE", raising=False)
    monkeypatch.setenv("KIWOOM_MODE", "real")

    class DenySupervisor:
        def allow(self, intent, context):  # type: ignore[no-untyped-def]
            class R:
                allow = False
                reason = "denied_by_test"
            return R()

    pkt = {
        "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "order_api_id": "ORDER_SUBMIT"},
        "risk": {"open_positions": 0},
        "exec_context": {},
    }

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "decision_packet": pkt,
        "supervisor": DenySupervisor(),
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "denied_by_test"
