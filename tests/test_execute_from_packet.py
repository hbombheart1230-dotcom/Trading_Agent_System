from libs.risk.intent import TradeIntent, RiskContext, ExecutionContext, TradeDecisionPacket
from libs.core.api_response import ApiResponse
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


def test_execute_from_packet_maps_order_submit_to_kiwoom_buy_api_when_available(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"kt10000","title":"buy","method":"POST","path":"/api/dostk/ordr","params":{"body":[{"name":"stk_cd","required":true},{"name":"ord_qty","required":true},{"name":"trde_tp","required":true},{"name":"ord_uv","required":false}]}, "_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    captured = {}

    class CaptureExecutor:
        def execute(self, req):  # type: ignore[no-untyped-def]
            captured["api_id"] = getattr(req, "api_id", None)
            captured["path"] = getattr(req, "path", None)
            captured["body"] = dict(getattr(req, "body", {}) or {})

            class Result:
                payload = {"mode": "mock"}
                response = None
                meta = {}

            return Result()

    state = {
        "catalog_path": str(cat),
        "executor": CaptureExecutor(),
        "decision_packet": {
            "intent": {
                "action": "BUY",
                "symbol": "005930",
                "qty": 1,
                "price": 70000,
                "order_type": "limit",
                "order_api_id": "ORDER_SUBMIT",
            },
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is True
    assert captured["api_id"] == "kt10000"
    assert captured["path"] == "/api/dostk/ordr"
    assert captured["body"]["stk_cd"] == "005930"
    assert int(captured["body"]["ord_qty"]) == 1
    assert str(captured["body"]["trde_tp"]) == "0"


def test_execute_from_packet_extracts_order_id_and_broker_codes_from_response_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    class CaptureExecutor:
        def execute(self, req):  # type: ignore[no-untyped-def]
            class Result:
                response = ApiResponse.from_http(
                    200,
                    '{"ord_no":"A000123","msg_cd":"0000","msg1":"accepted"}',
                )
                meta = {"executor": "real", "url": "https://mockapi.kiwoom.com/api/dostk/ordr"}

            return Result()

    state = {
        "catalog_path": str(cat),
        "executor": CaptureExecutor(),
        "decision_packet": {
            "intent": {
                "action": "BUY",
                "symbol": "005930",
                "qty": 1,
                "price": 70000,
                "order_type": "limit",
                "order_api_id": "ORDER_SUBMIT",
            },
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    p = out["execution"]["payload"]
    assert out["execution"]["allowed"] is True
    assert out["execution"]["ok"] is True
    assert int(p["status_code"]) == 200
    assert p["order_id"] == "A000123"
    assert p["broker_code"] == "0000"
    assert p["broker_message"] == "accepted"
    assert p["response_payload"]["ord_no"] == "A000123"


def test_execute_from_packet_marks_ok_false_when_broker_code_nonzero(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    class CaptureExecutor:
        def execute(self, req):  # type: ignore[no-untyped-def]
            class Result:
                response = ApiResponse.from_http(
                    200,
                    '{"return_code":20,"return_msg":"rejected by broker"}',
                )
                meta = {"executor": "real", "url": "https://mockapi.kiwoom.com/api/dostk/ordr"}

            return Result()

    state = {
        "catalog_path": str(cat),
        "executor": CaptureExecutor(),
        "decision_packet": {
            "intent": {
                "action": "BUY",
                "symbol": "005930",
                "qty": 1,
                "price": 70000,
                "order_type": "limit",
                "order_api_id": "ORDER_SUBMIT",
            },
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is True
    assert out["execution"]["ok"] is False
    assert out["execution"]["reason"] == "broker_rejected:20"


def test_execute_from_packet_forces_market_order_in_mock_broker_http_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("EXECUTION_MODE", "real")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"kt10000","title":"buy","method":"POST","path":"/api/dostk/ordr","params":{"body":[{"name":"stk_cd","required":true},{"name":"ord_qty","required":true},{"name":"trde_tp","required":true},{"name":"ord_uv","required":false}]}, "_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    class AllowSupervisor:
        def allow(self, intent, context):  # type: ignore[no-untyped-def]
            class R:
                allow = True
                reason = "Allowed"
            return R()

    captured = {}

    class CaptureExecutor:
        def execute(self, req):  # type: ignore[no-untyped-def]
            captured["body"] = dict(getattr(req, "body", {}) or {})

            class Result:
                response = ApiResponse.from_http(200, '{"return_code":0,"return_msg":"ok"}')
                meta = {"executor": "real"}

            return Result()

    state = {
        "catalog_path": str(cat),
        "executor": CaptureExecutor(),
        "supervisor": AllowSupervisor(),
        "decision_packet": {
            "intent": {
                "action": "BUY",
                "symbol": "005930",
                "qty": 1,
                "price": 70000,
                "order_type": "limit",
                "order_api_id": "ORDER_SUBMIT",
            },
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is True
    assert out["execution"]["ok"] is True
    assert str(captured["body"]["trde_tp"]) == "3"
    assert str(captured["body"].get("ord_uv") or "") == ""
