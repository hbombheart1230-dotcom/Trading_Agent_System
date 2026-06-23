from __future__ import annotations

import json

from libs.reporting.evaluation.start_gate import _trade_gate
from libs.runtime.q9_decision_snapshots import (
    capture_commander_decision_snapshot,
    capture_scanner_decision_snapshot,
)


def test_q9_snapshot_upserts_scanner_and_commander_under_one_id(tmp_path) -> None:
    state = {
        "reports_root": str(tmp_path / "reports"),
        "run_id": "run-1",
        "ts": "2026-06-23T00:05:00+00:00",
        "now_epoch": 1782173100,
        "selected": {"symbol": "005930"},
        "scanner_output": {
            "top_stock": "005930",
            "ranked_candidates": [{"symbol": "005930", "rank": 1}],
        },
        "scanner_candidate_ranking_table": {
            "scanner_intrinsic_control_top10": [{"symbol": "000660", "rank": 1}],
            "post_strategist_top10": [{"symbol": "005930", "rank": 1}],
        },
        "strategist_output": {
            "run_id": "strategist-1",
            "playbook": "pullback",
        },
    }
    scanner_result = capture_scanner_decision_snapshot(state)
    state["monitor_output"] = {"intent_side": "BUY", "selected_symbol": "005930"}
    state["intents"] = [{"side": "BUY", "symbol": "005930"}]
    state["decision"] = "approve"
    state["decision_reason"] = "monitor_entry_within_policy"
    commander_result = capture_commander_decision_snapshot(state)

    assert scanner_result["decision_id"] == commander_result["decision_id"]
    payload = json.loads(
        (tmp_path / "reports" / "operator_summary" / "daily" / "2026-06-23" / "q9_decision_windows.json")
        .read_text(encoding="utf-8")
    )
    assert payload["window_count"] == 1
    window = payload["windows"][0]
    assert window["window_type"] == "scanner_selection"
    assert window["scanner_control"]["top1_symbol"] == "000660"
    assert window["strategist_selection"]["selected_symbol"] == "005930"
    assert window["commander_final"]["decision"] == "approve"
    assert state["scanner_output"]["q9_decision_snapshot"]["commander_final"]["decision"] == "approve"


def test_q9_snapshot_normalizes_numeric_timestamp(tmp_path) -> None:
    state = {
        "reports_root": str(tmp_path / "reports"),
        "run_id": "run-epoch",
        "ts": 1782173100,
        "selected": {"symbol": "005930"},
        "scanner_output": {"ranked_candidates": [{"symbol": "005930"}]},
        "scanner_candidate_ranking_table": {
            "scanner_intrinsic_control_top10": [{"symbol": "005930"}],
        },
    }

    capture_scanner_decision_snapshot(state)
    snapshot = state["q9_decision_snapshot"]

    assert snapshot["generated_at"].endswith("+00:00")
    assert snapshot["decision_epoch"] == 1782173100


def test_q9_commander_only_window_is_classified(tmp_path) -> None:
    state = {
        "reports_root": str(tmp_path / "reports"),
        "run_id": "hold-run",
        "ts": "2026-06-23T01:00:00+00:00",
        "selected": {"symbol": "005930"},
        "monitor_output": {"intent_side": "HOLD", "selected_symbol": "005930"},
        "decision": "noop",
    }

    capture_commander_decision_snapshot(state)

    assert state["q9_decision_snapshot"]["window_type"] == "commander_monitor_only"


def test_start_gate_accepts_intrinsic_ranking_control_but_labels_scope() -> None:
    row = _trade_gate(
        {
            "trade_id": "T1",
            "symbol": "005930",
            "entry": {"timestamp": "2026-06-23T00:05:00+00:00"},
            "exit": {"timestamp": "2026-06-23T00:20:00+00:00"},
            "selection": {
                "raw_scanner_snapshot_source": "scanner_intrinsic_control_snapshot",
                "raw_scanner_control_scope": "same_candidate_universe_ranking_only",
                "raw_scanner_universe_control_available": False,
                "raw_scanner_top10": [{"symbol": "000660"}],
                "post_strategist_top10": [{"symbol": "005930"}],
                "strategist_run_id": "S1",
                "commander_final_explicit": True,
            },
            "monitor": {
                "entry_decision_count": 1,
                "exit_decision_count": 1,
                "post_exit": {"checkpoints": {"+5m": {"status": "observed"}}},
            },
            "integrity": {"status": "PASS"},
            "baseline_versions": {
                "q8_contract": "q8",
                "q9_contract": "q9",
                "tactic_contract": "tactic",
                "strategist_prompt": "prompt",
                "cost_model": "cost",
                "strategy_policy": "policy",
            },
        }
    )
    assert row["checks"]["raw_scanner_control_snapshot"] is True
    assert row["ranking_only_control"] is True
    assert row["universe_control_available"] is False
