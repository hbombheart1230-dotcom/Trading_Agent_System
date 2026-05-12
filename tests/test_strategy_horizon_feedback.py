from __future__ import annotations

from libs.runtime.strategy_horizon_feedback import (
    build_commander_horizon_policy,
    build_exit_vs_strategy_intent,
    build_post_exit_shadow_placeholder,
    build_strategy_horizon_feedback,
    update_post_exit_shadow_with_price_observations,
)


def test_build_strategy_horizon_feedback_is_observability_only_and_defaults_intraday() -> None:
    payload = build_strategy_horizon_feedback(
        {},
        playbook="pullback",
        monitor_guidance="hold_through_noise",
        trade_aggressiveness="normal",
        risk_tone="normal",
    )

    assert payload["observability_only"] is True
    assert payload["strategy_horizon"] == "intraday"
    assert payload["expected_hold_window"]["min_sec"] == 300
    assert payload["monitor_handoff"]["do_not_force_hold"] is True
    assert payload["behavior_translation"]["strategy_horizon"] == "intraday"
    assert payload["behavior_translation"]["applied"] is False


def test_build_exit_vs_strategy_intent_marks_non_hard_early_exit_as_unproven() -> None:
    state = {
        "strategist_output": {
            "strategy_horizon_feedback": {
                "strategy_horizon": "intraday",
                "expected_hold_window": {"min_sec": 300, "target_sec": 1800, "max_sec": 14400},
            }
        }
    }

    out = build_exit_vs_strategy_intent(
        state=state,
        exit_info={"triggered": True, "reason": "take_profit", "position_age_seconds": 120},
        sell_submitted=True,
    )

    assert out["observability_only"] is True
    assert out["early_exit_flag"] is True
    assert out["exit_alignment"] == "early_unproven"


def test_build_commander_horizon_policy_caps_long_horizon_in_live_validation() -> None:
    proposal = build_strategy_horizon_feedback(
        {"strategy_horizon": "1_2day_swing"},
        playbook="breakout",
        monitor_guidance="hold_through_noise",
    )

    out = build_commander_horizon_policy(
        proposal,
        commander_context={"session_bias": "active_selection", "risk_mode": "balanced"},
        live_validation_mode=True,
    )

    assert out["owner"] == "commander"
    assert out["observability_only"] is True
    assert out["do_not_force_hold"] is True
    assert out["allow_behavior_change"] is False
    assert out["allow_behavior_translation"] is True
    assert out["strategy_horizon"] == "intraday"
    assert out["source_strategy_horizon"] == "1_2day_swing"
    assert out["strategist_horizon_proposal"]["strategy_horizon"] == "1_2day_swing"
    assert out["behavior_translation"]["applied"] is True
    assert out["monitor_handoff"]["review_cadence_sec"] > 0


def test_exit_vs_strategy_intent_prefers_commander_horizon_policy() -> None:
    commander_policy = build_commander_horizon_policy(
        {
            "strategy_horizon": "1_2day_swing",
            "expected_hold_window": {"min_sec": 3600, "target_sec": 86400, "max_sec": 172800},
        },
        live_validation_mode=True,
    )
    state = {
        "commander_horizon_policy": commander_policy,
        "strategist_output": {
            "strategy_horizon_feedback": {
                "strategy_horizon": "1_2day_swing",
                "expected_hold_window": {"min_sec": 3600, "target_sec": 86400, "max_sec": 172800},
            }
        },
    }

    out = build_exit_vs_strategy_intent(
        state=state,
        exit_info={"triggered": True, "reason": "take_profit", "position_age_seconds": 120},
        sell_submitted=True,
    )

    assert out["horizon_owner"] == "commander"
    assert out["strategy_horizon"] == "intraday"
    assert out["source_strategy_horizon"] == "1_2day_swing"
    assert out["commander_horizon_policy"]["owner"] == "commander"
    assert out["early_exit_flag"] is True
    assert out["behavior_translation"]["applied"] is True


def test_build_post_exit_shadow_placeholder_records_pending_checkpoints_for_closed_trade() -> None:
    out = build_post_exit_shadow_placeholder(
        status="closed",
        lifecycle_bundle={
            "symbol": "005930",
            "strategist": {
                "strategy_horizon_feedback": {
                    "strategy_horizon": "intraday",
                    "expected_hold_window": {"min_sec": 300, "target_sec": 1800, "max_sec": 14400},
                }
            },
        },
        lifecycle={"exit": {"ts": "2026-04-27T10:14:00+09:00"}},
        exit_execution_details={"filled_price": 70000},
    )

    assert out["status"] == "pending"
    assert out["strategy_horizon"] == "intraday"
    assert out["symbol"] == "005930"
    assert out["checkpoints"]["EOD"]["status"] == "pending"


def test_build_post_exit_shadow_placeholder_prefers_monitor_exit_price_when_fill_missing() -> None:
    out = build_post_exit_shadow_placeholder(
        status="closed",
        lifecycle_bundle={"symbol": "018880"},
        lifecycle={
            "exit": {
                "ts": "2026-05-06T04:24:26+00:00",
                "monitor_context": {"current_price": 5440, "average_price": 5394},
            }
        },
        exit_execution_details={"filled_price": None, "avg_price": 5394},
    )

    assert out["exit_price"] == 5440


def test_build_post_exit_shadow_placeholder_recovers_commander_policy_from_exit_intent() -> None:
    out = build_post_exit_shadow_placeholder(
        status="closed",
        lifecycle_bundle={"trade_id": "TRD_20260428_005010_02"},
        lifecycle={
            "exit": {"ts": "2026-04-28T06:17:30+00:00"},
            "hold": [
                {
                    "monitor_context": {
                        "current_price": 6910,
                        "exit_vs_strategy_intent": {
                            "schema_version": "exit_vs_strategy_intent.v1",
                            "horizon_owner": "commander",
                            "strategy_horizon": "intraday",
                            "source_strategy_horizon": "intraday",
                            "expected_hold_window": {
                                "min_sec": 300,
                                "target_sec": 1800,
                                "max_sec": 14400,
                            },
                            "commander_horizon_policy": {
                                "schema_version": "commander_horizon_policy.v1",
                                "owner": "commander",
                                "strategy_horizon": "intraday",
                                "observability_only": True,
                                "do_not_force_hold": True,
                            },
                        },
                    }
                }
            ],
            "holding": {
                "monitor_context_snapshots": [
                    {
                        "current_price": 6900,
                        "exit_vs_strategy_intent": {
                            "schema_version": "exit_vs_strategy_intent.v1",
                            "horizon_owner": "strategist",
                            "strategy_horizon": "scalp",
                        },
                    }
                ]
            },
        },
        exit_execution_details={},
    )

    assert out["symbol"] == "005010"
    assert out["horizon_owner"] == "commander"
    assert out["commander_horizon_policy"]["owner"] == "commander"
    assert out["exit_price"] == 6910


def test_build_post_exit_shadow_placeholder_recovers_exit_intent_from_exit_context() -> None:
    out = build_post_exit_shadow_placeholder(
        status="closed",
        lifecycle_bundle={},
        lifecycle={
            "exit": {
                "symbol": "005380",
                "ts": "2026-04-28T06:17:30+00:00",
                "monitor_context": {
                    "current_price": 6910,
                    "exit_vs_strategy_intent": {
                        "schema_version": "exit_vs_strategy_intent.v1",
                        "horizon_owner": "commander",
                        "strategy_horizon": "intraday",
                        "source_strategy_horizon": "intraday",
                        "expected_hold_window": {
                            "min_sec": 300,
                            "target_sec": 1800,
                            "max_sec": 14400,
                        },
                        "commander_horizon_policy": {
                            "schema_version": "commander_horizon_policy.v1",
                            "owner": "commander",
                            "strategy_horizon": "intraday",
                            "observability_only": True,
                            "do_not_force_hold": True,
                        },
                    },
                },
            }
        },
        exit_execution_details={},
    )

    assert out["symbol"] == "005380"
    assert out["horizon_owner"] == "commander"
    assert out["commander_horizon_policy"]["owner"] == "commander"
    assert out["exit_price"] == 6910


def test_update_post_exit_shadow_with_price_observations_fills_checkpoint_prices() -> None:
    shadow = build_post_exit_shadow_placeholder(
        status="closed",
        lifecycle_bundle={"symbol": "005010"},
        lifecycle={"exit": {"ts": "2026-04-28T06:00:00+00:00"}},
        exit_execution_details={"filled_price": 1000},
    )

    out = update_post_exit_shadow_with_price_observations(
        shadow,
        minute_rows=[
            {"ts": "20260428060100", "close": 1005, "high": 1006, "low": 999, "volume": 10},
            {"ts": "20260428060500", "close": 1010, "high": 1015, "low": 998, "volume": 20},
            {"ts": "20260428061500", "close": 1020, "high": 1030, "low": 997, "volume": 30},
        ],
    )

    assert out["price_observation_status"] == "observed"
    assert out["checkpoints"]["+5m"]["status"] == "observed"
    assert out["checkpoints"]["+5m"]["price"] == 1010
    assert out["checkpoints"]["+5m"]["high_since_exit"] == 1015
    assert out["checkpoints"]["+5m"]["low_since_exit"] == 998
    assert round(out["checkpoints"]["+5m"]["return_pct"], 4) == 0.01
    assert out["checkpoints"]["+30m"]["status"] == "pending"
    assert out["best_exit_offset"] == "+15m"
    assert out["best_exit_price"] == 1030
