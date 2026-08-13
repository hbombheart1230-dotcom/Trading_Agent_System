from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.evaluation.start_gate import _trade_gate
from libs.runtime.q9_decision_snapshots import (
    capture_commander_decision_snapshot,
    capture_scanner_decision_snapshot,
)


def test_default_reports_root_is_isolated_during_pytest(
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "PYTEST_CURRENT_TEST",
        "tests/test_q9_decision_snapshots.py::test_default_reports_root_is_isolated",
    )
    monkeypatch.setenv("REPORTS_ROOT", "reports")
    state = {
        "run_id": "pytest-isolation",
        "ts": "2026-07-30T00:00:00+00:00",
        "scanner_output": {},
    }

    result = capture_scanner_decision_snapshot(state)

    assert "trading_agent_system_pytest" in result["path"]
    assert str(Path(result["path"])).endswith(
        str(Path("reports/operator_summary/daily/2026-07-30/q9_decision_windows.json"))
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
            "scanner_intrinsic_control_top20": [
                {"symbol": "000660", "rank": 1, "sources": ["top_value"]},
                {"symbol": "035420", "rank": 2, "sources": ["top_volume"]},
            ],
            "post_strategist_top10": [{"symbol": "005930", "rank": 1}],
            "pre_strategist_full_universe_snapshot": {
                "schema_version": "q9_scanner_pre_strategist_universe.v1",
                "candidate_count": 2,
                "intrinsic_ranked_top20": [
                    {
                        "symbol": "000660",
                        "rank": 1,
                        "sources": ["top_value"],
                        "source_scores": {"top_value": 0.8},
                        "source_observations": {
                            "top_change_rate": {
                                "schema_version": "kiwoom_top_change_rate_observation.v1",
                                "behavior_effect": "observation_only",
                                "api_id": "ka10027",
                                "source_rank": 1,
                                "captured_epoch": 1782173100,
                                "point_in_time": True,
                                "raw_fields": {"flu_rt": "+3.20", "cntr_str": "120.5"},
                                "normalized": {"change_rate_pct": 3.2, "execution_strength": 120.5},
                            }
                        },
                        "score_breakdown": {
                            "trading_value": 0.2,
                            "volume_surge": 0.1,
                        },
                        "compact_feature_snapshot": {
                            "engine_close_last": 198000,
                            "engine_signal_score": 0.8,
                        },
                    },
                    {"symbol": "035420", "rank": 2, "sources": ["top_volume"]},
                ],
            },
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
    assert [
        row["symbol"]
        for row in window["scanner_pre_strategist_universe"]["intrinsic_ranked_top20"]
    ] == ["000660", "035420"]
    assert (
        window["scanner_pre_strategist_universe"]["intrinsic_ranked_top20"][0]
        ["compact_feature_snapshot"]["engine_close_last"]
        == 198000
    )
    assert "engine_signal_score" not in (
        window["scanner_pre_strategist_universe"]["intrinsic_ranked_top20"][0]
        ["compact_feature_snapshot"]
    )
    first_pre = window["scanner_pre_strategist_universe"]["intrinsic_ranked_top20"][0]
    assert first_pre["sources"] == ["top_value"]
    assert first_pre["source_scores"] == {"top_value": 0.8}
    top_change = first_pre["source_observations"]["top_change_rate"]
    assert top_change["api_id"] == "ka10027"
    assert top_change["raw_fields"]["flu_rt"] == "+3.20"
    assert top_change["normalized"]["execution_strength"] == 120.5
    assert first_pre["score_breakdown"]["trading_value"] == 0.2
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


def test_q9_snapshot_preserves_monitor_noop_reason_and_directional_edge(
    tmp_path,
) -> None:
    state = {
        "reports_root": str(tmp_path / "reports"),
        "run_id": "noop-run",
        "ts": "2026-07-28T00:05:00+00:00",
        "selected": {"symbol": "005930"},
        "monitor_output": {
            "intent_side": "NOOP",
            "selected_symbol": "005930",
            "entry_exit_reason": "quant_entry_block:cost_edge_fail",
        },
        "monitor_entry": {
            "triggered": True,
            "guard_blocked": True,
            "guard_reason": "quant_entry_block:cost_edge_fail",
            "primary_failure_axis": "cost_adjusted_edge",
            "entry_lane": "strict",
            "entry_cost_filter": {
                "passed": False,
                "fail_reasons": ["estimated_gross_edge_below_cost_floor"],
            },
            "directional_edge_estimate": {
                "available": True,
                "reason": "eligible_historical_directional_expectancy",
                "expected_move_ratio": 0.000852,
            },
        },
        "decision": "approve",
        "decision_reason": "within_policy",
    }

    capture_commander_decision_snapshot(state)

    commander = state["q9_decision_snapshot"]["commander_final"]
    assert commander["monitor_intent"] == "NOOP"
    assert commander["monitor_reason"] == "quant_entry_block:cost_edge_fail"
    observation = commander["monitor_observation"]
    assert observation["entry_triggered"] is True
    assert observation["cost_filter_fail_reasons"] == [
        "estimated_gross_edge_below_cost_floor"
    ]
    assert observation["directional_edge_estimate"]["available"] is True


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
