from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from graphs.nodes.decision_node import decision_node
from graphs.nodes.execute_from_packet import execute_from_packet
from graphs.nodes.update_state_after_execution import update_state_after_execution
from libs.runtime.commander.execution import run_controlled_mock_lane_path
from libs.runtime.controlled_mock_lanes.ledger import load_attempts, load_submissions


KST = ZoneInfo("Asia/Seoul")
DAY = "2026-08-31"


def _epoch(hour: int, minute: int) -> int:
    return int(datetime(2026, 8, 31, hour, minute, tzinfo=KST).timestamp())


def _write_q12_candidate(root: Path) -> None:
    path = (
        root
        / "evaluation"
        / "baseline_btc_woori_tech"
        / DAY
        / "q12_btc_woori_hypothesis_validation.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "contract_id": "q12_btc_woori_five_variable_validation.v1",
                "day": DAY,
                "features": {
                    "btc_0855": {"status": "OBSERVED", "return_24h_pct": 5.2},
                    "btc_daily_context": {
                        "status": "OBSERVED",
                        "surge_state": "FIRST_SURGE",
                        "breakout_state": "60D_BREAKOUT",
                    },
                    "woori_opening": {"opening_gap_pct": 6.0},
                    "entry_methods": {
                        "09:03": {
                            "status": "OBSERVED",
                            "entry_epoch": _epoch(9, 3),
                            "entry_price": 6200.0,
                            "local_confirmation": True,
                            "volume_ratio": 1.4,
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )


def _intent_from_state(state: dict) -> dict:
    source = state["intents"][0]
    return {
        "action": source["side"],
        "symbol": source["symbol"],
        "qty": source["qty"],
        "price": source["price"],
        "order_type": "limit",
        "order_api_id": "ORDER_SUBMIT",
        "rationale": source["thesis"],
        "meta": source["meta"],
    }


def _packet(state: dict, *, intent: dict) -> dict:
    return {"intent": intent, "risk": state.get("risk_context") or {}, "exec_context": {}}


def test_q12_candidate_reaches_mock_broker_fill_without_strategist_or_scanner(
    tmp_path: Path, monkeypatch
) -> None:
    reports = tmp_path / "reports"
    ledger = tmp_path / "ledger"
    catalog = tmp_path / "api_catalog.jsonl"
    _write_q12_candidate(reports)
    catalog.write_text(
        '{"api_id":"ORDER_SUBMIT","title":"order","method":"POST","path":"/orders","params":{},"_flags":{"callable":true}}\n',
        encoding="utf-8",
    )
    captured = {}

    class MockKiwoomExecutor:
        def execute(self, request):  # type: ignore[no-untyped-def]
            captured["request"] = request

            class Result:
                payload = {
                    "api_ok": True,
                    "broker_code": "0000",
                    "broker_message": "accepted",
                    "order_id": "Q12-MOCK-1",
                    "filled_qty": 1,
                    "filled_price": 6200,
                }

            return Result()

    monkeypatch.setenv("KIWOOM_MODE", "mock")
    monkeypatch.setenv("EXECUTION_MODE", "real")
    monkeypatch.setenv("EXECUTION_ENABLED", "true")
    state = {
        "runtime_phase": "session",
        "now_epoch": _epoch(9, 5),
        "run_id": "integration-run",
        "catalog_path": str(catalog),
        "executor": MockKiwoomExecutor(),
        "recent_buy_guard_path": str(tmp_path / "recent_buy_guard.json"),
        "recent_sell_guard_path": str(tmp_path / "recent_sell_guard.json"),
        "portfolio_snapshot": {"positions": [], "open_positions": 0},
        "persisted_state": {"mock_positions": [], "mock_cash": 1_000_000.0},
        "policy": {"max_positions": 3},
        "risk_context": {"max_positions": 3},
        "intents": [],
    }

    result, executed = run_controlled_mock_lane_path(
        state,
        shadow_runtime={},
        decision_node_fn=decision_node,
        execute_fn=execute_from_packet,
        emit_trade_report_fn=lambda value: value,
        update_state_after_execution_fn=update_state_after_execution,
        intent_from_monitor_state_fn=_intent_from_state,
        build_packet_from_state_fn=_packet,
        reports_root=reports,
        ledger_root=ledger,
    )

    assert executed is True
    assert result["decision"] == "approve"
    assert result["execution"]["ok"] is True, result["execution"]
    assert result["execution"]["order_id"] == "Q12-MOCK-1"
    assert captured["request"].body["stk_cd"] == "041190"
    assert int(captured["request"].body["ord_qty"]) == 1
    assert result["persisted_state"]["mock_positions"][0]["symbol"] == "041190"
    assert result["persisted_state"]["mock_positions"][0]["qty"] == 1
    assert load_attempts(DAY, root=ledger)[0]["status"] == "BROKER_ACCEPTED"
    assert load_submissions(DAY, root=ledger)[0]["status"] == "FILLED"
