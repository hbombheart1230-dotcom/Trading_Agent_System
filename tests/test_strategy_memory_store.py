from __future__ import annotations

from pathlib import Path

from libs.research.strategy_memory_store import (
    load_recent_strategy_feedback,
    load_strategy_feedback_window,
    save_strategy_feedback,
    summarize_recent_feedback,
)


def _reporter_output(day: str, theme: str, *, pnl: float) -> dict:
    return {
        "day": day,
        "strategy_frame_summary": {
            "theme_top": {theme: 1},
            "playbook_top": {"pullback": 1},
            "risk_tone_top": {"normal": 1},
            "monitor_guidance_top": {"defensive_exit": 1},
            "report_focus_top": {"theme_accuracy": 1},
        },
        "strategist_evaluation": {
            "themes_proposed": [theme],
            "theme_alignment_status": "aligned",
            "assessment": "ok",
        },
        "scanner_evaluation": {
            "candidate_source_top": {"kiwoom_market_data": 2},
            "selected_symbol_top": {"005930": 1},
            "selection_status": "stable",
            "assessment": "ok",
        },
        "monitor_evaluation": {
            "monitor_status": "stable",
            "monitor_reason_top": {"hold": 1},
            "assessment": "ok",
        },
        "supervisor_activity": {
            "blocked_rate": 0.0,
            "blocked_reason_top": {},
            "assessment": "ok",
        },
        "incident_postmortem": {"incidents": []},
        "ai_findings": [f"{theme} aligned"],
        "ai_root_causes": [],
        "ai_improvement_suggestions": ["keep baseline"],
        "trade_summary": {
            "trade_count": 1,
            "symbols_traded": ["005930"],
            "symbol_hold_durations": [{"symbol": "005930", "holding_duration_sec": 300}],
            "decision_chain_run_total": 1,
        },
        "trade_decision_summaries": {
            "trade_summaries": [
                {
                    "symbol": "005930",
                    "holding_duration_sec": 300,
                    "estimated_realized_pnl": pnl,
                }
            ]
        },
        "report_focus_targets": ["theme_accuracy"],
        "operator_facing_summary": {"summary_lines": ["ok"], "recommended_actions": ["keep baseline"]},
        "market_context": {"global_sentiment_score": -0.1},
        "improvement_suggestions": ["keep baseline"],
        "report_json_path": f"reports/dev/analysis/reporter_analysis/reporter_analysis_{day}.json",
    }


def test_strategy_memory_store_save_load_and_window(tmp_path: Path) -> None:
    memory_path = tmp_path / "strategy_memory" / "feedback.jsonl"

    save_strategy_feedback(
        "reporter-2026-03-10",
        _reporter_output("2026-03-10", "semiconductor", pnl=1.25),
        path=memory_path,
        timestamp="2026-03-10T15:30:00+00:00",
    )
    save_strategy_feedback(
        "reporter-2026-03-11",
        _reporter_output("2026-03-11", "defense", pnl=-0.5),
        path=memory_path,
        timestamp="2026-03-11T15:30:00+00:00",
    )

    recent = load_recent_strategy_feedback(1, path=memory_path)
    assert len(recent) == 1
    assert recent[0]["run_id"] == "reporter-2026-03-11"

    window = load_strategy_feedback_window(
        "2026-03-10T00:00:00+00:00",
        "2026-03-10T23:59:59+00:00",
        path=memory_path,
    )
    assert len(window) == 1
    assert window[0]["run_id"] == "reporter-2026-03-10"

    summary = summarize_recent_feedback(5, path=memory_path)
    assert summary["feedback_window_size"] == 2
    assert "reporter-2026-03-10" in summary["run_ids"]
    assert summary["top_improvement_suggestions"] == ["keep baseline", "keep baseline"]
