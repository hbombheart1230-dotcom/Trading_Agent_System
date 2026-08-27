from __future__ import annotations

import json

from graphs.commander_runtime import _run_integrated_chain
from libs.runtime.monitor_strategy_frame import position_strategy_frame_for_symbol
from libs.runtime.position_horizon_revision import (
    apply_strategist_horizon_revision,
    initialize_horizon_state,
)
from libs.runtime.stage3_horizon_lineage import (
    record_stage3_assessment,
    record_stage3_invocation,
    record_stage3_response,
)


def _position_context() -> dict:
    output = {
        "strategy_horizon": "scalp",
        "commander_horizon_policy": {
            "schema_version": "commander_horizon_policy.v1",
            "owner": "commander",
            "strategy_horizon": "scalp",
            "expected_hold_window": {"min_sec": 60, "target_sec": 300, "max_sec": 900},
        },
    }
    return {
        "output": output,
        "generated_epoch": 1_000,
        "source": "buy_execution",
        "horizon_state": initialize_horizon_state(output, now_epoch=1_000),
    }


def test_stage3_lineage_records_full_observability_chain(tmp_path) -> None:
    state = {
        "run_id": "stage3-lineage-run",
        "day": "2026-08-27",
        "now_epoch": 2_000,
        "reports_root": str(tmp_path),
        "commander_decision": {
            "strategist_refresh_context": {
                "refresh_scope": "open_position_monitor_refresh",
                "refresh_trigger": "horizon_review_due",
                "selected_symbol": "005930",
            }
        },
        "persisted_state": {"position_strategy_context": {"005930": _position_context()}},
    }
    context = state["persisted_state"]["position_strategy_context"]["005930"]
    record_stage3_assessment(
        state,
        {
            "position_refresh_due": True,
            "position_refresh_trigger": "horizon_review_due",
            "override_action": "strategist_refresh",
            "refresh_cooldown_symbol": "005930",
            "positions": [
                {
                    "symbol": "005930",
                    "position_age_seconds": 1_000,
                    "hold_repeat_count": 4,
                    "horizon_review_due": True,
                    "position_horizon_state": context["horizon_state"],
                }
            ],
        },
    )
    record_stage3_invocation(state)
    state["strategist_output"] = {
        "stale_intraday_hold_review": {
            "hold_review_decision": "hold",
            "horizon_action": "extend",
            "current_horizon": "scalp",
            "proposed_horizon": "intraday",
            "revised_hold_window": {"min_sec": 300, "target_sec": 2_400, "max_sec": 7_200},
            "evidence_confidence": "high",
            "data_quality": "ok",
            "next_check_minutes": 15,
        }
    }
    state["strategist_llm"] = {"status": "ok", "stage_response_ref": "response.json"}
    record_stage3_response(state)

    apply_strategist_horizon_revision(state, now_epoch=2_000)
    frame = position_strategy_frame_for_symbol(state, "005930", {})

    assert frame["entry_horizon"] == "scalp"
    assert frame["active_horizon"] == "intraday"
    lineage = state["stage3_horizon_lineage"]
    row = lineage["records"][0]
    assert row["scheduling"]["review_due"] is True
    assert row["invocation"]["target_symbol"] == "005930"
    assert row["response"]["horizon_action"] == "extend"
    assert row["commander_application"]["approved"] is True
    assert row["commander_application"]["active_horizon_before"] == "scalp"
    assert row["commander_application"]["active_horizon_after"] == "intraday"
    assert row["commander_application"]["horizon_changed"] is True
    assert row["monitor_consumption"]["consumed"] is True
    assert row["monitor_consumption"]["active_horizon"] == "intraday"
    assert row["consistency_issues"] == []

    path = tmp_path / "canonical" / "2026-08-27" / "stage3-lineage-run" / "stage3_horizon_lineage.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "stage3_horizon_lineage.v1"
    assert payload["records"][0]["monitor_consumption"]["consumed"] is True


def test_stage3_lineage_surfaces_exit_advisory_without_forwarding(tmp_path) -> None:
    state = {
        "run_id": "stage3-exit-advisory",
        "day": "2026-08-27",
        "now_epoch": 2_000,
        "reports_root": str(tmp_path),
        "commander_decision": {
            "strategist_refresh_context": {
                "refresh_scope": "open_position_monitor_refresh",
                "selected_symbol": "005930",
            }
        },
        "persisted_state": {"position_strategy_context": {"005930": _position_context()}},
        "strategist_output": {
            "stale_intraday_hold_review": {
                "hold_review_decision": "exit_now",
                "horizon_action": "request_exit",
                "evidence_confidence": "high",
                "data_quality": "ok",
            }
        },
    }
    record_stage3_invocation(state)
    record_stage3_response(state)
    apply_strategist_horizon_revision(state, now_epoch=2_000)

    row = state["stage3_horizon_lineage"]["records"][0]
    assert row["commander_application"]["exit_request_forwarded"] is False
    assert "exit_advisory_not_forwarded" in row["consistency_issues"]


def test_stage3_lineage_records_cooldown_skip_reason(tmp_path) -> None:
    state = {
        "run_id": "stage3-cooldown-skip",
        "day": "2026-08-27",
        "now_epoch": 2_000,
        "reports_root": str(tmp_path),
    }
    record_stage3_assessment(
        state,
        {
            "position_refresh_due": False,
            "override_suppressed": True,
            "override_suppressed_reason": "repeated_hold_monitor_only_refresh_cooldown",
            "refresh_cooldown_symbol": "005930",
            "positions": [
                {
                    "symbol": "005930",
                    "hold_repeat_count": 4,
                    "horizon_review_due": False,
                    "position_horizon_state": _position_context()["horizon_state"],
                }
            ],
        },
    )

    invocation = state["stage3_horizon_lineage"]["records"][0]["invocation"]
    assert invocation["requested"] is False
    assert invocation["status"] == "skipped"
    assert invocation["reason"] == "repeated_hold_monitor_only_refresh_cooldown"


def test_stage3_lineage_write_failure_is_non_fatal(tmp_path) -> None:
    blocking_file = tmp_path / "not-a-directory"
    blocking_file.write_text("blocked", encoding="utf-8")
    state = {
        "run_id": "stage3-write-failure",
        "day": "2026-08-27",
        "reports_root": str(blocking_file),
        "commander_decision": {
            "strategist_refresh_context": {
                "refresh_scope": "open_position_monitor_refresh",
                "selected_symbol": "005930",
            }
        },
    }

    assert record_stage3_invocation(state) == ""
    assert "stage3_horizon_lineage_write_error" in state


def test_integrated_commander_path_calls_stage3_and_monitor_consumes_revision(monkeypatch, tmp_path) -> None:
    calls: list[str] = []

    def fake_portfolio(state: dict) -> dict:
        calls.append("portfolio")
        state["portfolio_snapshot"] = {
            "cash": 1_000_000.0,
            "positions": [
                {
                    "symbol": "005930",
                    "qty": 1,
                    "avg_price": 70_000.0,
                    "current_price": 70_100.0,
                    "account_pnl_ratio": 0.0014,
                }
            ],
            "_health": {"reader_ok": True},
        }
        return state

    def fake_risk(state: dict) -> dict:
        calls.append("risk")
        return state

    def fake_strategist(state: dict) -> dict:
        calls.append("strategist")
        context = state["commander_decision"]["strategist_refresh_context"]
        assert context["refresh_scope"] == "open_position_monitor_refresh"
        assert context["selected_symbol"] == "005930"
        state["strategist_output"] = {
            "stale_intraday_hold_review": {
                "hold_review_decision": "hold",
                "horizon_action": "extend",
                "current_horizon": "scalp",
                "proposed_horizon": "intraday",
                "revised_hold_window": {"min_sec": 300, "target_sec": 2_400, "max_sec": 7_200},
                "evidence_confidence": "high",
                "data_quality": "ok",
                "next_check_minutes": 15,
            }
        }
        return state

    def fake_scanner(state: dict) -> dict:
        calls.append("scanner")
        state.pop("selected", None)
        state["scanner_output"] = {"ranked_candidates": []}
        return state

    def fake_monitor(state: dict) -> dict:
        calls.append("monitor")
        frame = position_strategy_frame_for_symbol(state, "005930", {})
        assert frame["entry_horizon"] == "scalp"
        response = (
            state.get("stage3_horizon_lineage", {}).get("records", [{}])[0].get("response", {})
            if state.get("stage3_horizon_lineage", {}).get("records")
            else {}
        )
        assert frame["active_horizon"] == ("intraday" if response.get("present") else "scalp")
        state["monitor_output"] = {
            "selected_symbol": "005930",
            "intent_side": "NOOP",
            "entry_exit_reason": "hold",
        }
        state["intents"] = []
        return state

    def fake_decision(state: dict) -> dict:
        calls.append("decision")
        state["decision"] = "hold"
        return state

    monkeypatch.setattr("graphs.nodes.build_portfolio_snapshot.build_portfolio_snapshot", fake_portfolio)
    monkeypatch.setattr("graphs.nodes.build_risk_context.build_risk_context", fake_risk)
    monkeypatch.setattr("graphs.nodes.strategist_node.strategist_node", fake_strategist)
    monkeypatch.setattr("graphs.nodes.scanner_node.scanner_node", fake_scanner)
    monkeypatch.setattr("graphs.nodes.monitor_node.monitor_node", fake_monitor)
    monkeypatch.setattr("graphs.nodes.decision_node.decision_node", fake_decision)
    monkeypatch.setattr("graphs.commander_runtime._hydrate_monitor_symbol_features", lambda state: state)

    context = _position_context()
    out = _run_integrated_chain(
        {
            "run_id": "stage3-integrated-run",
            "day": "2026-08-27",
            "now_epoch": 2_000,
            "reports_root": str(tmp_path),
            "applied_policy": {
                "commander": {"route": {"monitor_only_when_holding": True}},
                "risk": {"max_positions": 1},
            },
            "persisted_state": {
                "position_strategy_context": {"005930": context},
                "monitor_last_state_by_symbol": {"005930": {"posture": "hold", "reason": "hold"}},
                "commander_open_position_hold_repeat_by_symbol": {"005930": 2},
            },
        },
        execute_fn=lambda state: state,
    )

    horizon = out["persisted_state"]["position_strategy_context"]["005930"]["horizon_state"]
    row = out["stage3_horizon_lineage"]["records"][0]
    assert horizon["active_horizon"] == "intraday"
    assert row["scheduling"]["review_due"] is True
    assert row["invocation"]["requested"] is True
    assert row["response"]["present"] is True
    assert row["commander_application"]["horizon_changed"] is True
    assert row["monitor_consumption"]["consumed"] is True
    assert row["consistency_issues"] == []
    assert calls == [
        "portfolio",
        "risk",
        "monitor",
        "decision",
        "strategist",
        "scanner",
        "monitor",
        "decision",
    ]
