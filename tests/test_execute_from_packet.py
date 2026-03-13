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
    assert out["execution"]["payload"]["execution_mode"] == "mock"
    assert out["execution"]["payload"]["kiwoom_mode"] == "mock"
    assert out["execution"]["payload"]["broker_env"] == "mock"
    assert out["execution"]["payload"]["effective_mode"] == "mock_executor"


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


def test_execute_from_packet_blocks_symbol_not_allowlisted(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setenv("SYMBOL_ALLOWLIST", "005930")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "000660", "qty": 1, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "symbol_not_allowlisted"
    assert int(out["execution"]["symbol_guard"]["allowlist_size"]) == 1


def test_execute_from_packet_blocks_qty_limit_with_max_qty_alias(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setenv("MAX_ORDER_QTY", "")
    monkeypatch.setenv("MAX_QTY", "1")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "005930", "qty": 2, "price": 70000, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "order_qty_limit_exceeded"
    assert out["execution"]["order_limit_guard"]["max_qty_key"] == "MAX_QTY"


def test_execute_from_packet_blocks_notional_limit_with_max_notional_alias(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "")
    monkeypatch.setenv("MAX_NOTIONAL", "100000")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "005930", "qty": 2, "price": 70000, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "order_notional_limit_exceeded"
    assert out["execution"]["order_limit_guard"]["max_notional_key"] == "MAX_NOTIONAL"


def test_execute_from_packet_allows_sell_even_when_qty_exceeds_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setenv("MAX_ORDER_QTY", "")
    monkeypatch.setenv("MAX_QTY", "1")
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "")
    monkeypatch.setenv("MAX_NOTIONAL", "100000")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "portfolio_snapshot": {
            "cash": 1_000_000.0,
            "positions": [{"symbol": "005930", "qty": 20, "avg_price": 70000.0}],
        },
        "decision_packet": {
            "intent": {"action": "SELL", "symbol": "005930", "qty": 20, "price": 70000, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 1},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is True
    assert out["execution"]["payload"]["mode"] == "mock"


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
    assert out["execution"]["payload"]["mode"] == "real"
    assert out["execution"]["payload"]["execution_mode"] == "real"
    assert out["execution"]["payload"]["kiwoom_mode"] == "mock"
    assert out["execution"]["payload"]["broker_env"] == "mock"
    assert out["execution"]["payload"]["effective_mode"] == "mock_broker_http"
    assert str(captured["body"]["trde_tp"]) == "3"
    assert str(captured["body"].get("ord_uv") or "") == ""


def test_execute_from_packet_blocks_buy_when_portfolio_snapshot_reader_failed(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "real")
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("PORTFOLIO_SNAPSHOT_HEALTH_GUARD_ENABLED", "true")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    class AllowSupervisor:
        def allow(self, intent, context):  # type: ignore[no-untyped-def]
            class R:
                allow = True
                reason = "allowed"

            return R()

    called = {"execute": 0}

    class CaptureExecutor:
        def execute(self, req):  # type: ignore[no-untyped-def]
            called["execute"] += 1

            class Result:
                response = ApiResponse.from_http(200, '{"return_code":0,"return_msg":"ok"}')
                meta = {"executor": "real"}

            return Result()

    state = {
        "catalog_path": str(cat),
        "supervisor": AllowSupervisor(),
        "executor": CaptureExecutor(),
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [],
            "_health": {
                "reader_ok": False,
                "reader_error": "account_api_500",
                "source": "mock_fallback_after_reader_error",
            },
        },
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
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "portfolio_snapshot_reader_error"
    assert out["execution"]["portfolio_guard"]["reader_ok"] is False
    assert called["execute"] == 0
