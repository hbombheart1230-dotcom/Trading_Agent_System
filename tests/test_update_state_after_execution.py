import time
from graphs.nodes.update_state_after_execution import update_state_after_execution


def test_update_state_does_not_touch_last_order_on_blocked():
    state = {"persisted_state": {"last_order_epoch": 10}, "execution": {"ok": False, "blocked": True, "reason": "cooldown"}}
    out = update_state_after_execution(state)
    assert out["persisted_state"]["last_order_epoch"] == 10
    assert out["persisted_state"]["last_execution_ok"] is False


def test_update_state_updates_last_order_on_ok_real(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {"persisted_state": {"last_order_epoch": 10}, "execution": {"ok": True, "dry_run": False, "reason": "sent"}}
    out = update_state_after_execution(state)
    assert out["persisted_state"]["last_order_epoch"] == 1234
    assert out["persisted_state"]["last_execution_ok"] is True


def test_update_state_does_not_update_last_order_on_ok_dry_run(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {"persisted_state": {"last_order_epoch": 10}, "execution": {"ok": True, "dry_run": True, "reason": "dry-run"}}
    out = update_state_after_execution(state)
    assert out["persisted_state"]["last_order_epoch"] == 10


def test_update_state_handles_allowed_schema_real(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {
        "persisted_state": {"last_order_epoch": 10},
        "execution": {"allowed": True, "payload": {"mode": "real"}, "reason": "Allowed"},
    }
    out = update_state_after_execution(state)
    assert out["persisted_state"]["last_execution_ok"] is True
    assert out["persisted_state"]["last_order_epoch"] == 1234


def test_update_state_handles_allowed_schema_mock_without_order_sent(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {
        "persisted_state": {"last_order_epoch": 10},
        "execution": {"allowed": True, "payload": {"mode": "mock"}, "reason": "Allowed"},
    }
    out = update_state_after_execution(state)
    assert out["persisted_state"]["last_execution_ok"] is True
    assert out["persisted_state"]["last_order_epoch"] == 10


def test_update_state_mock_buy_updates_mock_positions(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {
        "strategist_output": {"playbook": "defensive", "monitor_guidance": "defensive_exit"},
        "persisted_state": {"last_order_epoch": 10, "mock_positions": []},
        "execution": {
            "allowed": True,
            "payload": {"mode": "mock"},
            "reason": "Allowed",
            "order": {"action": "BUY", "symbol": "005930", "qty": 2, "price": 70000},
        },
    }
    out = update_state_after_execution(state)
    ps = out["persisted_state"]
    assert ps["last_order_epoch"] == 10
    assert ps["open_positions"] == 1
    assert ps["mock_positions"][0]["symbol"] == "005930"
    assert ps["mock_positions"][0]["qty"] == 2
    assert ps["mock_positions"][0]["avg_price"] == 70000.0
    assert ps["mock_cash"] == 1860000.0
    assert ps["mock_realized_pnl"] == 0.0
    assert ps["position_peak_price"] == {"005930": 70000.0}
    assert ps["position_entry_epoch_by_symbol"] == {"005930": 1234}
    assert ps["mock_positions"][0]["position_entry_epoch"] == 1234
    assert ((ps.get("position_strategy_context") or {}).get("005930") or {}).get("output", {}).get("playbook") == "defensive"
    assert ps["last_trade_side"] == "BUY"
    assert ps["last_trade_epoch"] == 1234
    assert ps["last_trade_symbol"] == "005930"


def test_update_state_mock_buy_uses_selected_quote_when_order_price_missing(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {
        "selected": {"symbol": "005930", "features": {"skill_quote_price": 70100}},
        "persisted_state": {"last_order_epoch": 10, "mock_positions": []},
        "execution": {
            "allowed": True,
            "payload": {"mode": "mock"},
            "reason": "Allowed",
            "order": {"action": "BUY", "symbol": "005930", "qty": 1, "price": None},
        },
    }
    out = update_state_after_execution(state)
    ps = out["persisted_state"]
    assert ps["open_positions"] == 1
    assert ps["mock_positions"][0]["avg_price"] == 70100.0
    assert ps["mock_cash"] == 1929900.0


def test_update_state_mock_sell_closes_position(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {
        "persisted_state": {
            "last_order_epoch": 10,
            "mock_positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "unrealized_pnl": 0.0}],
            "position_peak_price": {"005930": 71200.0},
            "position_strategy_context": {
                "005930": {"output": {"playbook": "defensive"}, "generated_epoch": 1200, "source": "buy_execution"}
            },
            "position_entry_epoch_by_symbol": {"005930": 1000},
            "mock_cash": 1860000.0,
            "mock_realized_pnl": 0.0,
        },
        "execution": {
            "allowed": True,
            "payload": {"mode": "mock"},
            "reason": "Allowed",
            "order": {"action": "SELL", "symbol": "005930", "qty": 2, "price": 70200},
        },
    }
    out = update_state_after_execution(state)
    ps = out["persisted_state"]
    assert ps["open_positions"] == 0
    assert ps["mock_positions"] == []
    assert ps.get("position_peak_price") in ({}, None)
    assert ps.get("position_strategy_context") in ({}, None)
    assert ps.get("position_entry_epoch_by_symbol") in ({}, None)
    assert ps["mock_cash"] == 2000400.0
    assert ps["mock_realized_pnl"] == 400.0
    assert ps["last_trade_side"] == "SELL"
    assert ps["last_trade_epoch"] == 1234
    assert ps["last_trade_symbol"] == "005930"


def test_update_state_mock_sell_uses_market_snapshot_when_order_price_missing(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {
        "market_snapshot": {"symbol": "005930", "price": 70200.0},
        "persisted_state": {
            "last_order_epoch": 10,
            "mock_positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "unrealized_pnl": 0.0}],
            "position_peak_price": {"005930": 70800.0},
            "mock_cash": 1860000.0,
            "mock_realized_pnl": 0.0,
        },
        "execution": {
            "allowed": True,
            "payload": {"mode": "mock"},
            "reason": "Allowed",
            "order": {"action": "SELL", "symbol": "005930", "qty": 2, "price": None},
        },
    }
    out = update_state_after_execution(state)
    ps = out["persisted_state"]
    assert ps["open_positions"] == 0
    assert ps["mock_positions"] == []
    assert ps.get("position_peak_price") in ({}, None)
    assert ps["mock_cash"] == 2000400.0
    assert ps["mock_realized_pnl"] == 400.0


def test_update_state_real_mode_still_updates_mock_ledger_when_kiwoom_mode_mock(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    state = {
        "persisted_state": {"last_order_epoch": 10, "mock_positions": [], "mock_cash": 2000000.0},
        "execution": {
            "allowed": True,
            "payload": {"mode": "real"},
            "reason": "Allowed",
            "order": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 70000},
        },
    }
    out = update_state_after_execution(state)
    ps = out["persisted_state"]
    assert ps["last_order_epoch"] == 1234
    assert ps["open_positions"] == 1
    assert ps["mock_positions"][0]["symbol"] == "005930"
    assert ps["mock_positions"][0]["qty"] == 1


def test_update_state_does_not_apply_fill_when_broker_rejected(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    state = {
        "persisted_state": {"last_order_epoch": 10, "mock_positions": [], "mock_cash": 2000000.0},
        "execution": {
            "allowed": True,
            "payload": {"mode": "real", "api_ok": True, "broker_code": "20"},
            "reason": "broker_rejected:20",
            "order": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 70000},
        },
    }
    out = update_state_after_execution(state)
    ps = out["persisted_state"]
    assert ps["last_execution_ok"] is False
    assert ps["last_order_epoch"] == 10
    assert ps.get("mock_positions") == []
    assert ps.get("mock_cash") == 2000000.0


def test_update_state_tracks_mock_broker_restricted_symbol_on_rc4007_buy_reject(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    monkeypatch.setattr(time, "strftime", lambda _fmt: "2026-03-31")
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    state = {
        "persisted_state": {"last_order_epoch": 10, "mock_positions": [], "mock_cash": 2000000.0},
        "execution": {
            "allowed": True,
            "payload": {
                "mode": "real",
                "api_ok": True,
                "broker_code": "20",
                "broker_message": "[2000](RC4007:모의투자 매매제한 종목입니다.)",
            },
            "reason": "broker_rejected:20",
            "order": {"action": "BUY", "symbol": "252670", "qty": 1, "price": 10000},
        },
    }
    out = update_state_after_execution(state)
    ps = out["persisted_state"]
    assert ps["last_execution_ok"] is False
    assert (ps.get("mock_broker_restricted_symbols") or {}).get("252670", {}).get("broker_code") == "20"
    assert "모의투자 매매제한 종목" in (
        (ps.get("mock_broker_restricted_symbols") or {}).get("252670", {}).get("broker_message") or ""
    )


def test_update_state_reconciles_stale_mock_position_on_sell_reject_code20(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    monkeypatch.setenv("KIWOOM_MODE", "mock")
    state = {
        "persisted_state": {
            "last_order_epoch": 10,
            "mock_positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "unrealized_pnl": 0.0}],
            "position_peak_price": {"005930": 71100.0},
            "mock_cash": 2000000.0,
        },
        "execution": {
            "allowed": True,
            "payload": {"mode": "real", "api_ok": True, "broker_code": "20"},
            "reason": "broker_rejected:20",
            "order": {"action": "SELL", "symbol": "005930", "qty": 2, "price": 70200},
        },
    }
    out = update_state_after_execution(state)
    ps = out["persisted_state"]
    assert ps["last_execution_ok"] is False
    assert ps.get("mock_positions") == []
    assert ps.get("open_positions") == 0
    assert ps.get("position_peak_price") in ({}, None)
    assert ps.get("mock_position_desync_reconciled") is True


def test_update_state_mock_partial_sell_preserves_existing_position_peak(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {
        "persisted_state": {
            "last_order_epoch": 10,
            "mock_positions": [{"symbol": "005930", "qty": 3, "avg_price": 70000.0, "unrealized_pnl": 0.0}],
            "position_peak_price": {"005930": 71500.0},
            "position_entry_epoch_by_symbol": {"005930": 1000},
            "mock_cash": 1790000.0,
            "mock_realized_pnl": 0.0,
        },
        "execution": {
            "allowed": True,
            "payload": {"mode": "mock"},
            "reason": "Allowed",
            "order": {"action": "SELL", "symbol": "005930", "qty": 1, "price": 70500},
        },
    }

    out = update_state_after_execution(state)
    ps = out["persisted_state"]
    assert ps["open_positions"] == 1
    assert ps["mock_positions"][0]["qty"] == 2
    assert ps["position_peak_price"] == {"005930": 71500.0}
    assert ps["position_entry_epoch_by_symbol"] == {"005930": 1000}


def test_update_state_mock_buy_stores_position_strategy_context(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {
        "strategist_output": {"playbook": "defensive", "monitor_guidance": "defensive_exit"},
        "persisted_state": {"last_order_epoch": 10, "mock_positions": []},
        "execution": {
            "allowed": True,
            "payload": {"mode": "mock"},
            "reason": "Allowed",
            "order": {"action": "BUY", "symbol": "005930", "qty": 1, "price": 70000},
        },
    }

    out = update_state_after_execution(state)
    context = ((out["persisted_state"].get("position_strategy_context") or {}).get("005930") or {})
    assert context.get("source") == "buy_execution"
    assert (context.get("output") or {}).get("playbook") == "defensive"


def test_update_state_sanitizes_stale_position_strategy_context(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {
        "persisted_state": {
            "mock_positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "unrealized_pnl": 0.0}],
            "position_strategy_context": {
                "005930": {"output": {"playbook": "defensive"}, "generated_epoch": 1000, "source": "buy_execution"},
                "000660": {"output": {"playbook": "breakout"}, "generated_epoch": 1000, "source": "buy_execution"},
            },
        },
        "execution": {"ok": False, "blocked": True, "reason": "noop"},
    }

    out = update_state_after_execution(state)
    ps = out["persisted_state"]
    assert set((ps.get("position_strategy_context") or {}).keys()) == {"005930"}


def test_update_state_sanitizes_stale_position_peak_price(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {
        "persisted_state": {
            "mock_positions": [{"symbol": "005930", "qty": 2, "avg_price": 70000.0, "unrealized_pnl": 0.0}],
            "position_peak_price": {"005930": 71000.0, "000660": 130000.0, "A0082N0": 1000.0},
        },
        "execution": {"ok": False, "blocked": True, "reason": "noop"},
    }

    out = update_state_after_execution(state)
    ps = out["persisted_state"]
    assert ps["position_peak_price"] == {"005930": 71000.0}


def test_update_state_sanitizes_invalid_mock_positions_and_last_trade_symbol(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {
        "persisted_state": {
            "mock_positions": [
                {"symbol": "0082N0", "qty": 1, "avg_price": 0.0, "unrealized_pnl": 0.0},
                {"symbol": "005930", "qty": 2, "avg_price": 70000.0, "unrealized_pnl": 0.0},
            ],
            "last_trade_symbol": "A0082N0",
        },
        "execution": {"ok": False, "blocked": True, "reason": "noop"},
    }

    out = update_state_after_execution(state)
    ps = out["persisted_state"]
    assert [row["symbol"] for row in ps["mock_positions"]] == ["005930"]
    assert ps["open_positions"] == 1
    assert ps.get("last_trade_symbol") in ("", None)


def test_update_state_adds_reasoning_trace_snapshot(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {
        "commander_decision": {
            "decision_summary": "Commander kept the session defensive.",
            "command_intent": "OBSERVE_ONLY",
            "strategist_invocation": "RUN",
            "llm_policy": "ALLOW",
            "no_trade_reason_code": "WAIT_FOR_CONFIRMATION",
            "source_priority": ["shadow_commander", "runtime_observation", "strategist_fallback"],
            "source_refs": {"shadow_event": "commander_router.shadow_assessment"},
            "shadow_used": True,
            "strategist_fallback_used": False,
        },
        "strategist_output": {
            "playbook": "defensive",
            "strategy_policy": {
                "market_policy": {},
                "scanner_policy": {},
                "monitor_policy": {},
                "decision_policy": {},
                "strategist_plan": {
                    "selected_playbook": "defensive",
                    "candidate_hypotheses": ["large_cap_defense"],
                    "symbol_constraints": {"max_beta": 1.1},
                    "strategy_summary": "Strategist stayed defensive.",
                },
                "provenance": {"shadow_used": True, "strategist_fallback_used": False},
            },
        },
        "scanner_output": {
            "selected_symbol": "003280",
            "runner_up_symbol": "000660",
            "ranking_factors": ["value", "trend"],
            "rejected_candidates": [{"symbol": "000660", "why": "lower score"}],
        },
        "scanner_candidate_selection_reason": {
            "selected_symbol": "003280",
            "selection_summary": "003280 ranked first.",
        },
        "monitor_output": {
            "decision": "WAIT",
            "action": "NONE",
            "entry_check_summary": "VWAP reclaim confirmation is pending.",
            "entry_blockers": ["below_vwap_reclaim_not_ready"],
            "timing_assessment": {"latest_candle_ts": 1774317480},
            "exit_trigger_basis": {"trigger_type": ""},
        },
        "persisted_state": {},
        "execution": {"ok": False, "blocked": True, "reason": "noop"},
    }

    out = update_state_after_execution(state)
    reasoning_trace = out["reasoning_trace"]
    provenance = out["reasoning_trace_provenance"]

    assert reasoning_trace["commander_summary"]["summary"] == "Commander kept the session defensive."
    assert reasoning_trace["strategist_summary"]["selected_playbook"] == "defensive"
    assert reasoning_trace["scanner_summary"]["selected_symbol"] == "003280"
    assert reasoning_trace["monitor_summary"]["summary"] == "VWAP reclaim confirmation is pending."
    assert provenance["shadow_used"] is True
    assert provenance["commander_source_ref"] == "commander_router.shadow_assessment"
    assert provenance["strategist_plan_source"] == "state.strategy_policy.strategist_plan"
    assert provenance["scanner_reason_source"] == "state.scanner_output"
    assert provenance["monitor_reason_source"] == "state.monitor_output"
    assert out["persisted_state"]["latest_reasoning_trace"] == reasoning_trace
    assert out["persisted_state"]["latest_reasoning_trace_provenance"] == provenance
    assert out["persisted_state"]["latest_reasoning_trace"]["scanner_summary"]["selected_symbol"] == "003280"


def test_update_state_remembers_recent_monitor_block_for_no_trade_cycle(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 1234.0)
    state = {
        "selected": {"symbol": "006340"},
        "monitor_output": {
            "action": "NONE",
            "selected_symbol": "006340",
            "primary_reason_code": "too_extended_from_vwap",
        },
        "persisted_state": {},
        "execution": {"ok": False, "blocked": True, "reason": "noop"},
    }

    out = update_state_after_execution(state)
    rows = list((out.get("persisted_state") or {}).get("recent_monitor_blocks") or [])
    assert len(rows) == 1
    assert rows[0]["symbol"] == "006340"
    assert rows[0]["reason"] == "too_extended_from_vwap"
    assert rows[0]["epoch"] == 1234
