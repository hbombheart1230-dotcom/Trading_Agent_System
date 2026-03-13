from __future__ import annotations

from libs.research.strategy_feedback_builder import build_recent_strategy_feedback


def test_strategy_feedback_builder_aggregates_recent_patterns() -> None:
    records = [
        {
            "run_id": "reporter-1",
            "strategist_evaluation": {
                "themes_proposed": ["semiconductor"],
                "theme_alignment_status": "aligned",
                "assessment": "aligned",
            },
            "strategy_frame_summary": {"playbook_top": {"breakout": 1}},
            "scanner_evaluation": {
                "candidate_source_top": {"kiwoom_market_data": 1},
                "selection_status": "stable",
                "assessment": "ok",
                "no_candidate_total": 0,
            },
            "monitor_evaluation": {
                "monitor_status": "stable",
                "monitor_reason_top": {"hold": 1},
                "rapid_buy_sell_cycles": 0,
                "assessment": "stable",
            },
            "supervisor_activity": {"blocked_rate": 0.1, "blocked_reason_top": {}},
            "incidents": [],
            "ai_root_causes": [],
            "operator_facing_summary": {"summary_lines": ["good run"]},
            "performance_summary": {"estimated_realized_pnl_total": 1.0},
            "trade_summary": {"trade_count": 1},
        },
        {
            "run_id": "reporter-2",
            "strategist_evaluation": {
                "themes_proposed": ["defense"],
                "theme_alignment_status": "partial",
                "assessment": "partial",
            },
            "strategy_frame_summary": {"playbook_top": {"pullback": 1}},
            "scanner_evaluation": {
                "candidate_source_top": {"kiwoom_market_data": 1},
                "selection_status": "needs_review",
                "assessment": "scanner weak",
                "no_candidate_total": 2,
            },
            "monitor_evaluation": {
                "monitor_status": "overtrading_risk",
                "monitor_reason_top": {"confirmed_exit_signal": 2},
                "rapid_buy_sell_cycles": 3,
                "min_hold_blocked_total": 1,
                "assessment": "monitor weak",
            },
            "supervisor_activity": {"blocked_rate": 0.5, "blocked_reason_top": {"max_notional": 2}},
            "incidents": [{"type": "rapid_cycle", "severity": "medium", "detail": "fast flip"}],
            "ai_root_causes": ["overtrading under weak pullback setup"],
            "operator_facing_summary": {"summary_lines": ["needs review"]},
            "performance_summary": {"estimated_realized_pnl_total": -0.7},
            "trade_summary": {"trade_count": 2},
        },
    ]

    out = build_recent_strategy_feedback(5, records=records)

    assert out["feedback_window_size"] == 2
    assert "semiconductor" in out["recent_theme_performance"]
    assert "breakout" in out["recent_playbook_performance"]
    assert any("overtrading" in item.lower() for item in out["recent_monitor_issues"])
    assert any("scanner" in item.lower() for item in out["recent_scanner_issues"])
    assert "max_notional" in out["recent_guard_patterns"]
    assert isinstance(out["recent_reporter_summary"], list)
    assert out["advisory_only"] is True
