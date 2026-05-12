import json

from libs.risk.intent import TradeIntent, RiskContext, ExecutionContext, TradeDecisionPacket
from libs.core.api_response import ApiResponse
from graphs.nodes.execute_from_packet import execute_from_packet
import graphs.nodes.execute_from_packet as execute_from_packet_module
import libs.runtime.asset_universe_policy as asset_universe_policy


def test_execute_from_packet_mock(tmp_path, monkeypatch):
    # ensure mock executor
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    # minimal catalog
    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"주문","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "order_api_id": "ORDER_SUBMIT", "order_type": "market"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is True
    assert out["execution"]["payload"]["mode"] == "mock"
    assert out["execution"]["payload"]["execution_mode"] == "mock"
    assert out["execution"]["payload"]["kiwoom_mode"] == "mock"
    assert out["execution"]["payload"]["broker_env"] == "mock"
    assert out["execution"]["payload"]["effective_mode"] == "mock_executor"


def test_execute_from_packet_blocks_new_buy_inside_entry_closeout_buffer(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "market_context": {"minutes_to_close": 10.5},
        "applied_policy": {
            "monitor": {"exit": {"eod_flat": {"enabled": True, "cutoff_min": 10}}},
        },
        "decision_packet": {
            "intent": {
                "action": "BUY",
                "symbol": "005930",
                "qty": 1,
                "price": 70000,
                "order_api_id": "ORDER_SUBMIT",
                "order_type": "market",
            },
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)

    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "buy_blocked_closeout_window"
    guard = out["execution"]["closeout_buy_guard"]
    assert guard["minutes_to_close"] == 10.5
    assert guard["eod_flat_cutoff_min"] == 10
    assert guard["buy_closeout_cutoff_min"] == 15


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


def test_execute_from_packet_blocks_invalid_symbol_format(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "0082N0", "qty": 1, "price": 70000, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "invalid_symbol_format"
    assert out["execution"]["symbol_format_guard"]["raw_symbol"] == "0082N0"


def test_execute_from_packet_blocks_buy_when_asset_universe_policy_rejects_etf(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "applied_policy": {"universe": {"asset_type": "common_stock_only"}},
        "symbol_metadata": {
            "069500": {
                "name": "KODEX 200 ETF",
            }
        },
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "069500", "qty": 1, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "asset_universe_policy_blocked"
    guard = out["execution"]["asset_universe_guard"]
    assert guard["excluded_by_asset_policy"] is True
    assert guard["exclusion_reason"] == "etf_or_etn_not_allowed"
    assert guard["asset_class_detected"] == "etf"
    assert guard["detection_source"] == "name_heuristic_extended"


def test_execute_from_packet_blocks_buy_when_remote_symbol_profile_identifies_etf(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    monkeypatch.setattr(
        asset_universe_policy,
        "_lookup_remote_symbol_profile",
        lambda symbol: {"stk_cd": str(symbol), "stk_nm": "TIGER 반도체TOP10"},
    )

    state = {
        "catalog_path": str(cat),
        "applied_policy": {"universe": {"asset_type": "common_stock_only"}},
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "396500", "qty": 1, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "asset_universe_policy_blocked"
    guard = out["execution"]["asset_universe_guard"]
    assert guard["excluded_by_asset_policy"] is True
    assert guard["asset_class_detected"] == "etf"
    assert guard["detection_source"] == "name_heuristic_extended"
    assert guard["detection_field"] == "remote_symbol_profile"
    assert (state.get("symbol_metadata") or {}).get("396500", {}).get("stk_nm") == "TIGER 반도체TOP10"


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


def test_execute_from_packet_blocks_notional_limit_using_selected_price_when_order_price_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "1000000")
    monkeypatch.setenv("MAX_NOTIONAL", "")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "selected": {"symbol": "000660", "price": 1_300_000},
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "000660", "qty": 1, "price": None, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "order_notional_limit_exceeded"
    guard = out["execution"]["order_limit_guard"]
    assert guard["price"] == 1_300_000
    assert guard["price_source"] == "selected.price"
    assert guard["order_notional"] == 1_300_000


def test_execute_from_packet_uses_monitor_price_for_notional_guard_when_order_price_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "1000000")
    monkeypatch.setenv("MAX_NOTIONAL", "")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "monitor_output": {
            "symbol": "033790",
            "current_price": 16920.0,
            "price_source": "state.minute_ohlcv_by_symbol.close",
        },
        "decision_packet": {
            "intent": {
                "action": "BUY",
                "symbol": "033790",
                "qty": 88,
                "price": None,
                "order_type": "market",
                "order_api_id": "ORDER_SUBMIT",
            },
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "order_notional_limit_exceeded"
    guard = out["execution"]["order_limit_guard"]
    assert guard["price"] == 16920.0
    assert guard["price_source"] == "monitor_output.current_price"
    assert guard["order_notional"] == 1_488_960


def test_execute_from_packet_uses_canonical_monitor_price_for_notional_guard_when_state_price_missing(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "1500000")
    monkeypatch.setenv("MAX_NOTIONAL", "")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )
    monitor_path = tmp_path / "reports" / "canonical" / "2026-05-07" / "run-1" / "monitor.json"
    monitor_path.parent.mkdir(parents=True)
    monitor_path.write_text(
        json.dumps({"agent": "monitor", "symbol": "000660", "current_price": 1_611_000.0}),
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "canonical_artifacts": {"monitor": str(monitor_path)},
        "decision_packet": {
            "intent": {
                "action": "BUY",
                "symbol": "000660",
                "qty": 1,
                "price": None,
                "order_type": "market",
                "order_api_id": "ORDER_SUBMIT",
            },
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    guard = out["execution"]["order_limit_guard"]
    assert guard["price"] == 1_611_000.0
    assert guard["price_source"] == "canonical.monitor.current_price"
    assert out["execution"]["reason"] == "order_notional_limit_exceeded"


def test_execute_from_packet_blocks_buy_when_notional_guard_price_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")
    monkeypatch.setenv("MAX_ORDER_NOTIONAL", "1000000")
    monkeypatch.setenv("MAX_NOTIONAL", "")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "000660", "qty": 1, "price": None, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "order_notional_price_missing"
    guard = out["execution"]["order_limit_guard"]
    assert guard["price_evaluable"] is False
    assert guard["limit_exceeded"] == "notional_price_missing"


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


def test_build_order_from_intent_uses_monitor_meta_price_when_price_missing():
    order = execute_from_packet_module._build_order_from_intent(
        {
            "action": "SELL",
            "symbol": "018880",
            "qty": 275,
            "price": None,
            "order_api_id": "ORDER_SUBMIT",
            "meta": {
                "price": 5440,
                "effective_price": 5351.38,
                "avg_price": 5394,
            },
        }
    )

    assert order["price"] == 5440
    assert order["meta"]["avg_price"] == 5394


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


def test_execute_from_packet_blocks_recent_same_symbol_buy_before_position_reflects(tmp_path, monkeypatch):
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
                response = ApiResponse.from_http(200, '{"ord_no":"A000123","msg_cd":"0000","msg1":"accepted"}')
                meta = {"executor": "real"}

            return Result()

    base_state = {
        "catalog_path": str(cat),
        "supervisor": AllowSupervisor(),
        "executor": CaptureExecutor(),
        "recent_buy_guard_path": str(tmp_path / "recent_buy_guard.json"),
        "recent_buy_guard_ttl_sec": 600,
        "runtime_mode": "integrated_chain",
        "runtime_phase": "session",
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [],
            "_health": {
                "reader_ok": True,
                "source": "reader",
                "positions_source": "reader_positions_authoritative_empty",
                "reconciliation_status": "reader_aligned",
                "reader_positions_authoritative": True,
                "positions_mismatch_detected": False,
                "reconciliation_applied": False,
                "reader_positions_count": 0,
                "persisted_positions_count": 0,
            },
        },
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 70000, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out1 = execute_from_packet({**base_state, "now_epoch": 1000})
    assert out1["execution"]["allowed"] is True
    assert out1["execution"]["execution_ok"] is True
    assert out1["execution"]["recent_buy_order_guard"]["updated"] is True

    out2 = execute_from_packet({**base_state, "now_epoch": 1060})
    assert out2["execution"]["allowed"] is False
    assert out2["execution"]["reason"] == "duplicate_buy_recent_order_exists"
    assert out2["execution"]["recent_buy_order_guard"]["remaining_sec"] == 540
    assert called["execute"] == 1


def test_execute_from_packet_blocks_recent_full_sell_before_position_reflects(tmp_path, monkeypatch):
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
                response = ApiResponse.from_http(200, '{"ord_no":"S000123","msg_cd":"0000","msg1":"accepted"}')
                meta = {"executor": "real"}

            return Result()

    base_state = {
        "catalog_path": str(cat),
        "supervisor": AllowSupervisor(),
        "executor": CaptureExecutor(),
        "recent_sell_guard_path": str(tmp_path / "recent_sell_guard.json"),
        "recent_sell_guard_ttl_sec": 180,
        "runtime_mode": "integrated_chain",
        "runtime_phase": "session",
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "005930", "qty": 10, "avg_price": 284500.0}],
            "_health": {
                "reader_ok": True,
                "source": "reader",
                "positions_source": "reader_positions_authoritative",
                "reconciliation_status": "reader_aligned",
                "reader_positions_authoritative": True,
                "positions_mismatch_detected": False,
                "reconciliation_applied": False,
                "reader_positions_count": 1,
                "persisted_positions_count": 1,
            },
        },
        "decision_packet": {
            "intent": {
                "action": "SELL",
                "symbol": "005930",
                "qty": 10,
                "price": 285500,
                "order_api_id": "ORDER_SUBMIT",
                "meta": {"position_qty": 10, "exit_qty": 10},
            },
            "risk": {"open_positions": 1},
            "exec_context": {},
        },
    }

    out1 = execute_from_packet({**base_state, "now_epoch": 1000})
    assert out1["execution"]["allowed"] is True
    assert out1["execution"]["execution_ok"] is True
    assert out1["execution"]["recent_sell_order_guard"]["remaining_qty_hint"] == 0

    out2 = execute_from_packet({**base_state, "now_epoch": 1060})
    assert out2["execution"]["allowed"] is False
    assert out2["execution"]["reason"] == "duplicate_sell_recent_full_exit_exists"
    assert out2["execution"]["recent_sell_order_guard"]["remaining_sec"] == 120
    assert called["execute"] == 1


def test_execute_from_packet_allows_recent_partial_sell_remaining_qty(tmp_path, monkeypatch):
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
                response = ApiResponse.from_http(200, '{"ord_no":"S000124","msg_cd":"0000","msg1":"accepted"}')
                meta = {"executor": "real"}

            return Result()

    common = {
        "catalog_path": str(cat),
        "supervisor": AllowSupervisor(),
        "executor": CaptureExecutor(),
        "recent_sell_guard_path": str(tmp_path / "recent_sell_guard.json"),
        "recent_sell_guard_ttl_sec": 180,
        "runtime_mode": "integrated_chain",
        "runtime_phase": "session",
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [{"symbol": "115160", "qty": 433, "avg_price": 6891.0}],
            "_health": {
                "reader_ok": True,
                "source": "reader",
                "positions_source": "reader_positions_authoritative",
                "reconciliation_status": "reader_aligned",
                "reader_positions_authoritative": True,
                "positions_mismatch_detected": False,
                "reconciliation_applied": False,
                "reader_positions_count": 1,
                "persisted_positions_count": 1,
            },
        },
        "risk": {"open_positions": 1},
        "exec_context": {},
    }

    first = {
        **common,
        "decision_packet": {
            "intent": {
                "action": "SELL",
                "symbol": "115160",
                "qty": 15,
                "price": 6900,
                "order_api_id": "ORDER_SUBMIT",
                "meta": {"position_qty": 433, "exit_qty": 15, "partial_exit": True},
            },
            "risk": {"open_positions": 1},
            "exec_context": {},
        },
    }
    second = {
        **common,
        "decision_packet": {
            "intent": {
                "action": "SELL",
                "symbol": "115160",
                "qty": 418,
                "price": 6980,
                "order_api_id": "ORDER_SUBMIT",
                "meta": {"position_qty": 418, "exit_qty": 418},
            },
            "risk": {"open_positions": 1},
            "exec_context": {},
        },
    }

    out1 = execute_from_packet({**first, "now_epoch": 1000})
    assert out1["execution"]["recent_sell_order_guard"]["remaining_qty_hint"] == 418

    out2 = execute_from_packet({**second, "now_epoch": 1060})
    assert out2["execution"]["allowed"] is True
    assert out2["execution"]["execution_ok"] is True
    assert called["execute"] == 2


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


def test_execute_from_packet_blocks_buy_at_upper_limit_from_skill_quote(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "skill_results": {
            "market.quote": {
                "result": {
                    "action": "ready",
                    "data": {
                        "symbol": "005930",
                        "cur": 100000,
                        "best_ask": 0,
                        "best_bid": 100000,
                        "raw": {
                            "cntr_infr": [
                                {
                                    "cur_prc": "+100000",
                                    "upl_pric": "+100000",
                                    "pri_sel_bid_unit": "0",
                                    "pri_buy_bid_unit": "+100000",
                                    "pre_rt": "+30.00",
                                }
                            ]
                        },
                    },
                }
            }
        },
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "order_api_id": "ORDER_SUBMIT", "order_type": "market"},
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "upper_limit_buy_blocked"
    guard = out["execution"]["upper_limit_guard"]
    assert guard["at_upper_limit"] is True
    assert guard["limit_locked"] is True


def test_execute_from_packet_attempts_upper_limit_cancel_after_accept_when_requested(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "real")
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("PORTFOLIO_SNAPSHOT_HEALTH_GUARD_ENABLED", "true")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n'
        '{"api_id":"kt10003","title":"cancel","method":"POST","path":"/api/dostk/ordr","params":{"body":[{"name":"orig_ord_no","required":true},{"name":"stk_cd","required":true},{"name":"cncl_qty","required":true}]},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    class AllowSupervisor:
        def allow(self, intent, context):  # type: ignore[no-untyped-def]
            class R:
                allow = True
                reason = "allowed"
            return R()

    calls = {"guard": 0, "execute": 0}

    def fake_upper_limit_guard(state, order):  # type: ignore[no-untyped-def]
        calls["guard"] += 1
        if calls["guard"] == 1:
            return True, "", {"guard_applied": True, "symbol": "005930"}
        return False, "upper_limit_buy_blocked", {"guard_applied": True, "symbol": "005930", "at_upper_limit": True}

    monkeypatch.setattr(execute_from_packet_module, "_evaluate_upper_limit_buy_guard", fake_upper_limit_guard)

    class CaptureExecutor:
        def execute(self, req):  # type: ignore[no-untyped-def]
            calls["execute"] += 1
            if calls["execute"] == 1:
                class Result:
                    response = ApiResponse.from_http(200, '{"ord_no":"A000123","msg_cd":"0000","msg1":"accepted"}')
                    meta = {"executor": "real"}
                return Result()
            class Result:
                response = ApiResponse.from_http(200, '{"ord_no":"A000124","msg_cd":"0000","msg1":"cancel accepted"}')
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
                "reader_ok": True,
                "source": "reader",
                "positions_source": "reader_positions_authoritative_empty",
                "reconciliation_status": "reader_aligned",
                "reader_positions_authoritative": True,
                "positions_mismatch_detected": False,
                "reconciliation_applied": False,
                "reader_positions_count": 0,
                "persisted_positions_count": 0,
            },
        },
        "decision_packet": {
            "intent": {
                "action": "BUY",
                "symbol": "005930",
                "qty": 1,
                "price": 70000,
                "order_type": "market",
                "order_api_id": "ORDER_SUBMIT",
            },
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is True
    assert out["execution"]["ok"] is True
    assert calls["execute"] == 2
    cancel_info = out["execution"]["upper_limit_cancel"]
    assert cancel_info["attempted"] is True
    assert cancel_info["cancel_ok"] is True
    assert cancel_info["cancel"]["order"]["api_id"] == "kt10003"


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
    assert out["execution"]["order_id"] == "A000123"
    assert out["execution"]["ord_no"] == "A000123"
    assert out["execution"]["broker_code"] == "0000"
    assert out["execution"]["broker_message"] == "accepted"
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


def test_execute_from_packet_blocks_buy_for_mock_broker_restricted_symbol_record(tmp_path, monkeypatch):
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("EXECUTION_MODE", "real")
    monkeypatch.setattr(execute_from_packet_module.time, "strftime", lambda _fmt: "2026-03-31")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    class AllowSupervisor:
        def allow(self, intent, context):  # type: ignore[no-untyped-def]
            class R:
                allow = True
                reason = "Allowed"
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
        "executor": CaptureExecutor(),
        "supervisor": AllowSupervisor(),
        "persisted_state": {
            "mock_broker_restricted_symbols": {
                "252670": {
                    "symbol": "252670",
                    "broker_code": "20",
                    "broker_message": "[2000](RC4007:모의투자 매매제한 종목입니다.)",
                    "reason": "broker_rejected:20",
                    "detected_epoch": 1774930000,
                    "detected_date": "2026-03-31",
                }
            }
        },
        "decision_packet": {
            "intent": {
                "action": "BUY",
                "symbol": "252670",
                "qty": 1,
                "price": 10000,
                "order_type": "limit",
                "order_api_id": "ORDER_SUBMIT",
            },
            "risk": {"open_positions": 0},
            "exec_context": {},
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "mock_broker_restricted_symbol_blocked"
    assert out["execution"]["mock_broker_restricted_symbol_guard"]["symbol"] == "252670"
    assert out["execution"]["mock_broker_restricted_symbol_guard"]["blocked"] is True
    assert called["execute"] == 0


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


def test_execute_from_packet_blocks_buy_when_portfolio_snapshot_mismatch_unresolved(tmp_path, monkeypatch):
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
                "reader_ok": True,
                "source": "reader",
                "positions_source": "persisted_mock_positions",
                "reconciliation_status": "persisted_fallback",
                "reader_positions_authoritative": False,
                "positions_mismatch_detected": True,
                "reconciliation_applied": False,
                "reader_positions_count": 0,
                "persisted_positions_count": 1,
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
    assert out["execution"]["reason"] == "portfolio_snapshot_positions_mismatch_unresolved"
    assert out["execution"]["portfolio_guard"]["positions_mismatch_detected"] is True
    assert out["execution"]["portfolio_guard"]["reconciliation_applied"] is False
    assert called["execute"] == 0


def test_execute_from_packet_uses_strategy_policy_sizing_rail_in_supervisor(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "real")
    monkeypatch.setenv("KIWOOM_MODE", "real")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "catalog_path": str(cat),
        "portfolio_snapshot": {
            "cash": 2_000_000.0,
            "positions": [],
            "_health": {
                "reader_ok": True,
                "source": "reader",
                "positions_source": "reader_positions_authoritative_empty",
                "reconciliation_status": "reader_aligned",
                "reader_positions_authoritative": True,
                "positions_mismatch_detected": False,
                "reconciliation_applied": False,
                "reader_positions_count": 0,
                "persisted_positions_count": 0,
            },
        },
        "decision_packet": {
            "intent": {
                "action": "BUY",
                "symbol": "005930",
                "qty": 2,
                "price": 70000,
                "order_type": "limit",
                "order_api_id": "ORDER_SUBMIT",
            },
            "risk": {"open_positions": 0},
            "exec_context": {},
            "strategy_policy": {
                "schema_version": "strategy_policy.v1",
                "market_policy": {
                    "playbook": "defensive",
                    "risk_tone": "conservative",
                    "trade_aggressiveness": "low",
                    "defensive_mode": True,
                },
                "entry_policy": {
                    "position_sizing": {
                        "max_position_qty": 1,
                        "min_position_qty": 1,
                        "lot_size": 1,
                    }
                },
                "monitor_policy": {
                    "hard_risk_rails": {
                        "hard_stop_pct": 0.01,
                        "max_stop_pct_cap": 0.03,
                    }
                },
                "decision_policy": {
                    "use_strategy_v1_engine": True,
                    "allow_score_override": False,
                },
            },
        },
    }

    out = execute_from_packet(state)
    assert out["execution"]["allowed"] is False
    assert out["execution"]["reason"] == "Strategy policy max position qty exceeded"
    assert out["execution"]["strategy_policy_summary"]["playbook"] == "defensive"
    assert out["execution"]["supervisor_guard"]["policy_guard"] == "max_position_qty"


def test_execute_from_packet_traces_strategy_policy_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("EXECUTION_MODE", "mock")

    cat = tmp_path / "api_catalog.jsonl"
    cat.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )

    state = {
        "run_id": "trace-policy-r1",
        "catalog_path": str(cat),
        "decision_packet": {
            "intent": {"action": "BUY", "symbol": "005930", "qty": 1, "order_api_id": "ORDER_SUBMIT"},
            "risk": {"open_positions": 0},
            "exec_context": {},
            "strategy_policy_summary": {
                "schema_version": "strategy_policy.v1",
                "playbook": "pullback",
                "risk_tone": "conservative",
                "max_position_qty": 3,
            },
        },
    }

    out = execute_from_packet(state)
    ledger = out.get("decision_trace_ledger") or {}
    latest = ledger.get("latest_by_agent") or {}
    assert out["execution"]["strategy_policy_summary"]["playbook"] == "pullback"
    assert latest["supervisor"]["strategy_policy_summary"]["playbook"] == "pullback"
    assert latest["executor"]["strategy_policy_summary"]["playbook"] == "pullback"
