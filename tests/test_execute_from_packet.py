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


def test_execute_from_packet_skips_noop_intent(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "decision_packet": {
            "intent": {"action": "NOOP", "symbol": "005930", "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "noop_intent_skipped"


def test_execute_from_packet_blocks_duplicate_buy_in_mock(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "005930", "qty": 1, "avg_price": 70000.0}],
        },
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 1},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "duplicate_buy_position_exists"


def test_execute_from_packet_blocks_buy_when_mock_cash_insufficient(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "persisted_state": {"mock_cash": 10000.0, "mock_positions": []},
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 70000, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "insufficient_mock_cash"


def test_execute_from_packet_allows_buy_when_mock_cash_sufficient(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "persisted_state": {"mock_cash": 200000.0, "mock_positions": []},
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 70000, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is True
    assert out["execution"]["payload"]["mode"] == "mock"
