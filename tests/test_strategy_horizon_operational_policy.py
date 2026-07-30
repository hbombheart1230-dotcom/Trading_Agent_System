from __future__ import annotations

from libs.reporting.evaluation.horizon_contract import build_horizon_contract
from libs.runtime.monitor_strategy_frame import (
    apply_exit_policy_strategy_frame,
    apply_monitor_strategy_frame,
)
from libs.runtime.strategy_horizon_feedback import (
    build_commander_horizon_policy,
    normalize_operational_commander_horizon_policy,
)


def _frame(horizon: str) -> dict:
    policy = build_commander_horizon_policy(
        {"strategy_horizon": horizon},
        live_validation_mode=True,
    )
    return {
        "playbook": "pullback",
        "monitor_guidance": "quick_take_profit",
        "risk_tone": "normal",
        "trade_aggressiveness": "normal",
        "strategy_horizon": horizon,
        "commander_horizon_policy": policy,
    }


def test_monitor_uses_commander_canonical_intraday_window() -> None:
    applied = apply_monitor_strategy_frame(
        min_hold_sec=600,
        sell_cooldown_sec=300,
        confirm_ticks=2,
        frame=_frame("intraday"),
    )

    assert applied["horizon_behavior_enabled"] is True
    assert applied["min_hold_sec"] == 300
    assert applied["expected_hold_window"] == {
        "min_sec": 300,
        "target_sec": 1800,
        "max_sec": 14400,
    }

    exit_policy = apply_exit_policy_strategy_frame(
        state={},
        exit_policy_base={
            "stop_loss_pct": 0.03,
            "take_profit_pct": 0.05,
            "profit_time_stop_sec": 900,
            "max_hold_sec": 3600,
        },
        selected=None,
        position=None,
        frame=applied,
    )["policy"]
    assert exit_policy["profit_time_stop_sec"] == 1800
    assert exit_policy["max_hold_sec"] == 14400


def test_monitor_uses_long_horizon_without_live_validation_downgrade() -> None:
    applied = apply_monitor_strategy_frame(
        min_hold_sec=600,
        sell_cooldown_sec=300,
        confirm_ticks=2,
        frame=_frame("overnight_probe"),
    )

    assert applied["strategy_horizon"] == "overnight_probe"
    assert applied["min_hold_sec"] == 1800
    assert (
        applied["horizon_behavior_translation"]["overnight_allowed"] is True
    )


def test_horizon_read_model_prefers_commander_policy_over_nested_proposal() -> None:
    commander = build_commander_horizon_policy(
        {"strategy_horizon": "intraday"},
        live_validation_mode=True,
    )
    commander["strategist_horizon_proposal"] = {
        "schema_version": "strategy_horizon_feedback.v1",
        "strategy_horizon": "scalp",
        "expected_hold_window": {
            "min_sec": 60,
            "target_sec": 300,
            "max_sec": 900,
        },
    }

    contract = build_horizon_contract(
        bundle={},
        entry={},
        exit_row={},
        entry_artifact={},
        exit_artifact={},
        scanner_context={},
        strategist_context={},
        monitor_context={"commander_horizon_policy": commander},
    )

    assert contract["strategy_horizon"] == "intraday"
    assert contract["expected_hold_window"]["target_sec"] == 1800
    assert contract["source_path"].endswith("commander_horizon_policy")
    assert contract["allow_behavior_change"] is True
    assert contract["do_not_force_hold"] is True


def test_legacy_commander_policy_is_upgraded_without_changing_horizon() -> None:
    upgraded = normalize_operational_commander_horizon_policy(
        {
            "schema_version": "commander_horizon_policy.v1",
            "owner": "commander",
            "strategy_horizon": "1_2day_swing",
            "observability_only": True,
            "allow_behavior_change": False,
            "expected_hold_window": {
                "min_sec": 300,
                "target_sec": 1800,
                "max_sec": 14400,
            },
        },
        source="test",
    )

    assert upgraded["strategy_horizon"] == "1_2day_swing"
    assert upgraded["expected_hold_window"] == {
        "min_sec": 3600,
        "target_sec": 86400,
        "max_sec": 172800,
    }
    assert upgraded["observability_only"] is False
    assert upgraded["allow_behavior_change"] is True
    assert upgraded["operational_contract_migrated"] is True
