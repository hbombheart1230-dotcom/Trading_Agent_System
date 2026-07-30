from __future__ import annotations

from libs.runtime.monitor_candidate_cascade import build_entry_candidate_cascade_plan
from libs.runtime.monitor_runner_up_quality import evaluate_runner_up_entry_quality


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


def test_candidate_cascade_defaults_include_common_near_miss_reasons_with_rank_limit() -> None:
    for reason in ("pullback_below_vwap_reclaim_not_ready", "breakout_not_ready"):
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
        assert plan["max_priority_rank"] == 3


def test_candidate_cascade_blocks_immature_pullback_by_default() -> None:
    plan = build_entry_candidate_cascade_plan(
        selected_symbol="005930",
        ranked_candidates=_ranked_candidates(),
        scanner_output={},
        open_position_count=0,
        entry_guard_blocked=False,
        entry_triggered=False,
        entry_reason="pullback_not_mature",
        max_runner_ups=2,
        cascade_enabled=True,
    )

    assert plan["attempted"] is False
    assert plan["blocked_reason"] == "hard_entry_blocker_no_cascade"


def test_candidate_cascade_hard_blocks_volume_and_duplicate_symbol_guards() -> None:
    volume_plan = build_entry_candidate_cascade_plan(
        selected_symbol="005930",
        ranked_candidates=_ranked_candidates(),
        scanner_output={},
        open_position_count=0,
        entry_guard_blocked=False,
        entry_triggered=False,
        entry_reason="volume_confirmation_missing",
        max_runner_ups=2,
        cascade_enabled=True,
        cascade_allowed_reasons=["volume_confirmation_missing"],
    )
    duplicate_plan = build_entry_candidate_cascade_plan(
        selected_symbol="005930",
        ranked_candidates=_ranked_candidates(),
        scanner_output={},
        open_position_count=1,
        max_positions=1,
        entry_guard_blocked=True,
        entry_guard_reason="same_symbol_position_open",
        entry_triggered=False,
        entry_reason="",
        max_runner_ups=2,
        cascade_enabled=True,
    )

    assert volume_plan["attempted"] is False
    assert volume_plan["blocked_reason"] == "hard_entry_blocker_no_cascade"
    assert duplicate_plan["attempted"] is False
    assert duplicate_plan["blocked_reason"] == "max_positions_reached"


def test_candidate_cascade_hard_blocks_held_top_pick_even_when_capacity_remains() -> None:
    plan = build_entry_candidate_cascade_plan(
        selected_symbol="005930",
        ranked_candidates=_ranked_candidates(),
        scanner_output={},
        open_position_count=1,
        max_positions=3,
        entry_guard_blocked=True,
        entry_guard_reason="same_symbol_position_open",
        entry_triggered=False,
        entry_reason="breakout_not_ready",
        max_runner_ups=2,
        cascade_enabled=True,
    )

    assert plan["attempted"] is False
    assert plan["blocked_reason"] == "hard_entry_blocker_no_cascade"
    assert plan["hard_blocked_reason"] == "same_symbol_position_open"


def test_loss_reentry_block_excludes_top_pick_but_keeps_runner_review() -> None:
    plan = build_entry_candidate_cascade_plan(
        selected_symbol="005930",
        ranked_candidates=[
            {"symbol": "005930", "rank": 1, "score_total": 1.00},
            {"symbol": "000660", "rank": 2, "score_total": 0.95},
        ],
        scanner_output={},
        open_position_count=0,
        max_positions=3,
        entry_guard_blocked=True,
        entry_guard_reason="same_symbol_loss_reentry_blocked",
        entry_triggered=True,
        entry_reason="pullback_structure_above_vwap_with_volume_confirmation",
        max_runner_ups=2,
    )

    assert plan["candidate_specific_reentry_block"] is True
    assert plan["attempted"] is True
    assert [row["symbol"] for row in plan["runner_rows"]] == ["000660"]


def test_candidate_cascade_skips_runner_ups_above_rank_limit() -> None:
    candidates = [
        {"symbol": "005930", "rank": 1},
        {"symbol": "000660", "rank": 2},
        {"symbol": "035420", "rank": 3},
        {"symbol": "012340", "rank": 4},
    ]

    plan = build_entry_candidate_cascade_plan(
        selected_symbol="005930",
        ranked_candidates=candidates,
        scanner_output={},
        open_position_count=0,
        entry_guard_blocked=False,
        entry_triggered=False,
        entry_reason="breakout_not_ready",
        max_runner_ups=2,
        cascade_enabled=True,
    )

    assert plan["runner_up_symbols"] == ["000660", "035420"]
    assert "012340" not in plan["runner_up_symbols"]


def test_candidate_cascade_q15_caps_commander_expanded_runner_up_rank() -> None:
    candidates = [
        {"symbol": "005930", "rank": 1, "score_total": 1.00},
        {"symbol": "000660", "rank": 2, "score_total": 0.99},
        {"symbol": "035420", "rank": 3, "score_total": 0.98},
        {"symbol": "012340", "rank": 4, "score_total": 0.97},
        {"symbol": "034220", "rank": 5, "score_total": 0.96},
    ]

    plan = build_entry_candidate_cascade_plan(
        selected_symbol="005930",
        ranked_candidates=candidates,
        scanner_output={},
        open_position_count=0,
        entry_guard_blocked=False,
        entry_triggered=False,
        entry_reason="breakout_not_ready",
        max_runner_ups=4,
        cascade_enabled=True,
    )

    assert plan["requested_max_priority_rank"] == 5
    assert plan["max_priority_rank"] == 3
    assert plan["max_runner_ups"] == 2
    assert plan["runner_up_symbols"] == ["000660", "035420"]
    assert "012340" not in plan["runner_up_symbols"]
    assert "034220" not in plan["runner_up_symbols"]


def test_candidate_cascade_q15_blocks_large_score_gap_runner_up() -> None:
    candidates = [
        {"symbol": "005930", "rank": 1, "score_total": 1.20},
        {"symbol": "000660", "rank": 2, "score_total": 0.80},
        {"symbol": "035420", "rank": 3, "score_total": 1.05},
    ]

    plan = build_entry_candidate_cascade_plan(
        selected_symbol="005930",
        ranked_candidates=candidates,
        scanner_output={},
        open_position_count=0,
        entry_guard_blocked=False,
        entry_triggered=False,
        entry_reason="breakout_not_ready",
        max_runner_ups=2,
        cascade_enabled=True,
    )

    assert plan["runner_up_symbols"] == ["035420"]
    skipped = list(plan["skipped"])
    assert any(
        row.get("symbol") == "000660"
        and row.get("reason") == "q15_score_gap_above_runner_up_limit"
        and row.get("score_gap") > row.get("max_score_gap")
        for row in skipped
    )


def test_candidate_cascade_q15_blocks_runner_up_with_expected_hard_blocker() -> None:
    candidates = [
        {"symbol": "005930", "rank": 1, "score_total": 1.20},
        {
            "symbol": "000660",
            "rank": 2,
            "score_total": 1.15,
            "expected_monitor_block_reason": "below_vwap_reclaim_not_ready",
        },
        {"symbol": "035420", "rank": 3, "score_total": 1.10},
    ]

    plan = build_entry_candidate_cascade_plan(
        selected_symbol="005930",
        ranked_candidates=candidates,
        scanner_output={},
        open_position_count=0,
        entry_guard_blocked=False,
        entry_triggered=False,
        entry_reason="breakout_not_ready",
        max_runner_ups=2,
        cascade_enabled=True,
    )

    assert plan["runner_up_symbols"] == ["035420"]
    assert any(
        row.get("symbol") == "000660"
        and row.get("reason") == "q15_runner_up_expected_blocker"
        and row.get("expected_blocker") == "below_vwap_reclaim_not_ready"
        for row in plan["skipped"]
    )


def test_candidate_cascade_q15_allows_volume_insufficient_runner_up_to_reach_monitor() -> None:
    candidates = [
        {"symbol": "005930", "rank": 1, "score_total": 1.20},
        {
            "symbol": "000660",
            "rank": 2,
            "score_total": 1.15,
            "expected_monitor_block_reason": "volume_insufficient",
        },
    ]

    plan = build_entry_candidate_cascade_plan(
        selected_symbol="005930",
        ranked_candidates=candidates,
        scanner_output={},
        open_position_count=0,
        entry_guard_blocked=False,
        entry_triggered=False,
        entry_reason="breakout_not_ready",
        max_runner_ups=1,
        cascade_enabled=True,
    )

    assert plan["runner_up_symbols"] == ["000660"]
    assert not any(row.get("reason") == "q15_runner_up_expected_blocker" for row in plan["skipped"])


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
    assert plan["blocked_reason"] == "hard_entry_blocker_no_cascade"


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


def test_runner_up_quality_requires_own_cost_volume_and_chart_evidence() -> None:
    blocked = evaluate_runner_up_entry_quality(
        runner_row={"symbol": "000660", "rank": 2, "score_breakdown": {"turnover": 0.2}},
        runner_entry={
            "triggered": True,
            "intent_submitted": True,
            "cost_adjusted_edge_ok": False,
            "reason": "pullback_reclaim_above_vwap_with_rebound_confirmation",
            "metrics": {"volume_ok": True, "pullback_mature": True},
        },
    )
    passed = evaluate_runner_up_entry_quality(
        runner_row={"symbol": "000660", "rank": 2, "score_breakdown": {"turnover": 0.2}},
        runner_entry={
            "triggered": True,
            "intent_submitted": True,
            "cost_adjusted_edge_ok": True,
            "reason": "pullback_reclaim_above_vwap_with_rebound_confirmation",
            "entry_condition_path": "pullback_volume_path",
            "metrics": {"volume_ok": True, "pullback_mature": True},
        },
    )

    assert blocked["passed"] is False
    assert "cost_edge_ok" in blocked["failed_checks"]
    assert passed["passed"] is True
