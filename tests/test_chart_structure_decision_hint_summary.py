from libs.reporting.chart_structure_decision_hint_summary import (
    build_chart_structure_decision_hint_executive_line,
    build_chart_structure_decision_hint_executive_summary,
    build_chart_structure_decision_hint_summary,
)


def test_chart_structure_decision_hint_summary_handles_empty_runs_safely() -> None:
    out = build_chart_structure_decision_hint_summary([])

    assert out["schema_version"] == "chart_structure_decision_hint_summary.v1"
    assert out["run_count"] == 0
    assert out["available_run_count"] == 0
    assert out["applied_count"] == 0
    assert out["applied_rate"] == 0.0
    assert out["applied_examples"] == []
    assert out["notes"] == ["no_runs_available"]


def test_chart_structure_decision_hint_summary_aggregates_applied_blockers() -> None:
    out = build_chart_structure_decision_hint_summary(
        [
            {
                "run_id": "run-1",
                "legacy_entry_decision": "BUY",
                "legacy_entry_reason": "breakout_above_recent_high_with_vwap_structure_confirmation",
                "final_decision": "WAIT",
                "reason": "breakout_continuation_structure_guard_blocked",
                "entry_style": "breakout",
                "chart_structure_decision_hint": {
                    "available": True,
                    "applied": True,
                    "mode": "block",
                    "entry_style": "breakout",
                    "blocking_features": ["structure_hh_hl=weakening", "momentum_follow_through=moderate"],
                },
            },
            {
                "run_id": "run-2",
                "legacy_entry_decision": "BUY",
                "legacy_entry_reason": "pullback_ready_with_support_confirmation",
                "final_decision": "WAIT",
                "reason": "pullback_reversal_structure_guard_blocked",
                "entry_style": "pullback",
                "chart_structure_decision_hint": {
                    "available": True,
                    "applied": True,
                    "mode": "block",
                    "entry_style": "pullback",
                    "blocking_features": ["support_holding=lost"],
                },
            },
            {
                "run_id": "run-3",
                "final_decision": "BUY",
                "reason": "breakout_above_recent_high_with_vwap_structure_confirmation",
                "entry_style": "breakout",
                "chart_structure_decision_hint": {
                    "available": True,
                    "applied": False,
                    "mode": "none",
                    "entry_style": "breakout",
                    "blocking_features": [],
                },
            },
        ]
    )

    assert out["run_count"] == 3
    assert out["available_run_count"] == 3
    assert out["applied_count"] == 2
    assert out["applied_rate"] == 0.6667
    assert out["mode_counts"]["block"] == 2
    assert out["mode_counts"]["none"] == 1
    assert out["blocking_feature_counts"]["structure_hh_hl"] == 1
    assert out["blocking_feature_counts"]["momentum_follow_through"] == 1
    assert out["blocking_feature_counts"]["support_holding"] == 1
    assert out["top_blocking_features"] == [
        "structure_hh_hl",
        "momentum_follow_through",
        "support_holding",
    ]
    assert out["reason_counts_when_applied"]["breakout_continuation_structure_guard_blocked"] == 1
    assert out["reason_counts_when_applied"]["pullback_reversal_structure_guard_blocked"] == 1
    assert out["entry_style_counts_when_applied"]["breakout"] == 1
    assert out["entry_style_counts_when_applied"]["pullback"] == 1
    assert out["decision_counts_when_applied"]["WAIT"] == 2
    assert len(out["applied_examples"]) == 2
    assert out["applied_examples"][0]["run_id"] == "run-1"
    assert out["applied_examples"][0]["reason_transition"] == (
        "breakout_above_recent_high_with_vwap_structure_confirmation -> "
        "breakout_continuation_structure_guard_blocked"
    )
    assert out["applied_examples"][1]["blocking_features"] == ["support_holding=lost"]


def test_chart_structure_decision_hint_executive_summary_builds_compact_headline() -> None:
    summary = {
        "schema_version": "chart_structure_decision_hint_summary.v1",
        "run_count": 12,
        "available_run_count": 5,
        "applied_count": 2,
        "applied_rate": 0.4,
        "mode_counts": {"block": 2, "none": 3},
        "blocking_feature_counts": {"failed_breakout": 1, "momentum_follow_through": 1},
        "top_blocking_features": ["failed_breakout", "momentum_follow_through"],
        "applied_run_ids": ["r1", "r2"],
        "reason_counts_when_applied": {"breakout_continuation_structure_guard_blocked": 2},
        "entry_style_counts_when_applied": {"breakout": 2},
        "decision_counts_when_applied": {"WAIT": 2},
        "notes": [],
    }

    out = build_chart_structure_decision_hint_executive_summary(summary)

    assert out["schema_version"] == "chart_structure_decision_hint_executive_summary.v1"
    assert out["status"] == "active"
    assert out["top_blocking_features"] == ["failed_breakout", "momentum_follow_through"]
    assert "applied 2 times" in out["headline"]
    assert build_chart_structure_decision_hint_executive_line(summary) == out["headline"]


def test_chart_structure_summary_treats_noop_as_a_blocked_outcome() -> None:
    out = build_chart_structure_decision_hint_summary(
        [
            {
                "run_id": "run-noop",
                "legacy_entry_decision": "BUY",
                "legacy_entry_reason": "pullback_reversal_structure_guard_blocked",
                "final_decision": "NOOP",
                "reason": "pullback_reversal_structure_guard_blocked",
                "chart_structure_decision_hint": {
                    "available": True,
                    "applied": True,
                    "mode": "block",
                    "entry_style": "pullback",
                    "blocking_features": ["support_holding=lost"],
                },
            }
        ]
    )

    assert "applied_without_wait_decision_detected" not in out["notes"]
    executive = build_chart_structure_decision_hint_executive_summary(out)
    assert executive["status"] == "active"
