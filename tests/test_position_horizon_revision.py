from __future__ import annotations

from libs.runtime.position_horizon_revision import (
    active_horizon_policy_for_context,
    apply_strategist_horizon_revision,
    initialize_horizon_state,
    overlay_active_horizon_on_output,
    position_review_due,
)


def _context(horizon: str = "scalp") -> dict:
    output = {
        "strategy_horizon": horizon,
        "commander_horizon_policy": {
            "schema_version": "commander_horizon_policy.v1",
            "owner": "commander",
            "strategy_horizon": horizon,
            "expected_hold_window": {},
        },
    }
    return {
        "output": output,
        "generated_epoch": 1000,
        "source": "buy_execution",
        "horizon_state": initialize_horizon_state(output, now_epoch=1000),
    }


def test_stage3_revises_active_horizon_without_mutating_entry_horizon() -> None:
    state = {
        "run_id": "run-1",
        "commander_decision": {
            "strategist_refresh_context": {"selected_symbol": "005930"},
        },
        "persisted_state": {"position_strategy_context": {"005930": _context("scalp")}},
        "strategist_output": {
            "stale_intraday_hold_review": {
                "hold_review_decision": "hold",
                "horizon_action": "extend",
                "proposed_horizon": "intraday",
                "revised_hold_window": {"min_sec": 300, "target_sec": 2400, "max_sec": 7200},
                "next_check_minutes": 15,
                "evidence_confidence": "high",
                "data_quality": "ok",
                "reason": "trend and volume remain intact",
            }
        },
    }

    out = apply_strategist_horizon_revision(state, now_epoch=1600)
    horizon = out["persisted_state"]["position_strategy_context"]["005930"]["horizon_state"]

    assert horizon["entry_horizon"] == "scalp"
    assert horizon["active_horizon"] == "intraday"
    assert horizon["active_expected_hold_window"]["target_sec"] == 2400
    assert horizon["next_review_epoch"] == 2500


def test_stage3_cannot_authorize_overnight_horizon() -> None:
    state = {
        "run_id": "run-2",
        "commander_decision": {"strategist_refresh_context": {"selected_symbol": "005930"}},
        "persisted_state": {"position_strategy_context": {"005930": _context("intraday")}},
        "strategist_output": {
            "stale_intraday_hold_review": {
                "hold_review_decision": "hold",
                "horizon_action": "extend",
                "proposed_horizon": "overnight_probe",
                "evidence_confidence": "high",
                "data_quality": "ok",
            }
        },
    }

    out = apply_strategist_horizon_revision(state, now_epoch=2000)
    horizon = out["persisted_state"]["position_strategy_context"]["005930"]["horizon_state"]

    assert horizon["active_horizon"] == "intraday"
    assert horizon["revision_history"][-1]["approved"] is False


def test_stage4_authorizes_only_explicit_high_quality_carry_symbol() -> None:
    state = {
        "run_id": "run-3",
        "persisted_state": {
            "position_strategy_context": {
                "005930": _context("intraday"),
                "000660": _context("intraday"),
            }
        },
        "strategist_output": {
            "end_of_day_carry_review": {
                "portfolio_level_decision": "carry_only_best_one",
                "carry_review": [
                    {"symbol": "005930", "decision": "carry_overnight", "carry_confidence": "high"},
                    {"symbol": "000660", "decision": "carry_overnight", "carry_confidence": "high"},
                ],
            }
        },
    }

    out = apply_strategist_horizon_revision(state, now_epoch=3000)
    contexts = out["persisted_state"]["position_strategy_context"]

    assert contexts["005930"]["horizon_state"]["active_horizon"] == "overnight_probe"
    assert contexts["005930"]["horizon_state"]["stage4_carry_approved"] is True
    assert contexts["000660"]["horizon_state"]["active_horizon"] == "intraday"
    assert contexts["000660"]["horizon_state"]["stage4_carry_approved"] is False
    assert active_horizon_policy_for_context(contexts["005930"])["entry_horizon"] == "intraday"


def test_position_review_due_uses_horizon_schedule() -> None:
    row = _context("intraday")
    assert position_review_due(row, position_age_seconds=1700, now_epoch=2700) is False
    assert position_review_due(row, position_age_seconds=1800, now_epoch=2800) is True


def test_stage3_revision_is_idempotent_for_same_run() -> None:
    state = {
        "run_id": "same-run",
        "commander_decision": {"strategist_refresh_context": {"selected_symbol": "005930"}},
        "persisted_state": {"position_strategy_context": {"005930": _context("scalp")}},
        "strategist_output": {
            "stale_intraday_hold_review": {
                "hold_review_decision": "hold",
                "horizon_action": "extend",
                "proposed_horizon": "intraday",
                "next_check_minutes": 15,
                "evidence_confidence": "high",
                "data_quality": "ok",
            }
        },
    }
    apply_strategist_horizon_revision(state, now_epoch=1600)
    apply_strategist_horizon_revision(state, now_epoch=1700)
    horizon = state["persisted_state"]["position_strategy_context"]["005930"]["horizon_state"]

    assert len(horizon["revision_history"]) == 1
    assert horizon["next_review_epoch"] == 2500


def test_monitor_overlay_uses_active_horizon_and_preserves_entry_horizon() -> None:
    row = _context("scalp")
    row["horizon_state"]["active_horizon"] = "intraday"
    row["horizon_state"]["active_expected_hold_window"] = {
        "min_sec": 300,
        "target_sec": 2400,
        "max_sec": 7200,
    }

    output = overlay_active_horizon_on_output(row["output"], row)

    assert output["strategy_horizon"] == "intraday"
    assert output["commander_horizon_policy"]["entry_horizon"] == "scalp"
    assert output["expected_hold_window"]["target_sec"] == 2400
