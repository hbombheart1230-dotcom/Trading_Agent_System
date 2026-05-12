from __future__ import annotations

from libs.runtime.monitor_candidate_cascade import build_entry_candidate_cascade_plan


def _ranked_candidates():
    return [
        {"symbol": "005930", "rank": 1},
        {"symbol": "000660", "rank": 2},
        {"symbol": "035420", "rank": 3},
    ]


def test_candidate_cascade_respects_commander_allowed_reasons() -> None:
    plan = build_entry_candidate_cascade_plan(
        selected_symbol="005930",
        ranked_candidates=_ranked_candidates(),
        scanner_output={},
        open_position_count=0,
        entry_guard_blocked=False,
        entry_triggered=False,
        entry_reason="breakout_not_ready",
        max_runner_ups=1,
        cascade_enabled=True,
        cascade_allowed_reasons=["breakout_not_ready"],
        cascade_blocked_reasons=["cost_filter_failed"],
    )

    assert plan["attempted"] is True
    assert plan["runner_up_symbols"] == ["000660"]
    assert plan["max_runner_ups"] == 1


def test_candidate_cascade_defaults_include_common_near_miss_reasons() -> None:
    for reason in ("pullback_not_mature", "volume_confirmation_missing"):
        plan = build_entry_candidate_cascade_plan(
            selected_symbol="005930",
            ranked_candidates=_ranked_candidates(),
            scanner_output={},
            open_position_count=0,
            entry_guard_blocked=False,
            entry_triggered=False,
            entry_reason=reason,
            max_runner_ups=2,
            cascade_enabled=True,
        )

        assert plan["attempted"] is True
        assert plan["runner_up_symbols"] == ["000660", "035420"]


def test_candidate_cascade_stops_on_commander_blocked_reason() -> None:
    plan = build_entry_candidate_cascade_plan(
        selected_symbol="005930",
        ranked_candidates=_ranked_candidates(),
        scanner_output={},
        open_position_count=0,
        entry_guard_blocked=False,
        entry_triggered=False,
        entry_reason="cost_filter_failed",
        max_runner_ups=2,
        cascade_enabled=True,
        cascade_allowed_reasons=["cost_filter_failed"],
        cascade_blocked_reasons=["cost_filter_failed"],
    )

    assert plan["attempted"] is False
    assert plan["blocked_reason"] == "reason_cascade_blocked_by_policy"


def test_candidate_cascade_stops_when_entry_control_disables_cascade() -> None:
    plan = build_entry_candidate_cascade_plan(
        selected_symbol="005930",
        ranked_candidates=_ranked_candidates(),
        scanner_output={},
        open_position_count=0,
        entry_guard_blocked=False,
        entry_triggered=False,
        entry_reason="breakout_not_ready",
        max_runner_ups=2,
        cascade_enabled=False,
    )

    assert plan["attempted"] is False
    assert plan["max_runner_ups"] == 0
    assert plan["blocked_reason"] == "cascade_disabled_by_entry_control"
