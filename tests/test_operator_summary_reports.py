from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.operator_period_summary import (
    generate_operator_daily_summary_artifact,
    generate_operator_period_summary,
    generate_operator_symbol_summary_artifact,
)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_operator_weekly_and_monthly_summary_reports_use_operator_symbol_history(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write_json(
        reports / "operator_summary" / "symbols" / "005930" / "trade_history.json",
        [
            {
                "trade_id": "TRD_20260428_005930_01",
                "date": "2026-04-28",
                "symbol": "005930",
                "status": "closed",
                "entry_reason": "breakout_above_recent_high",
                "exit_reason": "SELL was triggered because peak_drawdown.",
                "entry_pattern_type": "breakout",
                "exit_pattern_type": "peak_drawdown",
                "result_pct": -0.5,
                "hold_seconds": 300,
            },
            {
                "trade_id": "TRD_20260429_005930_01",
                "date": "2026-04-29",
                "symbol": "005930",
                "status": "closed",
                "entry_reason": "pullback_rebound",
                "exit_reason": "SELL was triggered because take_profit.",
                "entry_pattern_type": "pullback",
                "exit_pattern_type": "take_profit",
                "result_pct": 1.0,
                "hold_seconds": 600,
            },
        ],
    )
    _write_json(
        reports / "operator_summary" / "symbols" / "000660" / "trade_history.json",
        [
            {
                "trade_id": "TRD_20260504_000660_01",
                "date": "2026-05-04",
                "symbol": "000660",
                "status": "closed",
                "entry_reason": "breakout_above_recent_high",
                "exit_reason": "SELL was triggered because hard_stop.",
                "entry_pattern_type": "breakout",
                "exit_pattern_type": "hard_stop",
                "result_pct": -1.0,
                "hold_seconds": 200,
            }
        ],
    )

    weekly_md, weekly_json, weekly = generate_operator_period_summary(
        reports_root=reports,
        period_type="weekly",
        period_key="2026-W18",
    )
    monthly_md, monthly_json, monthly = generate_operator_period_summary(
        reports_root=reports,
        period_type="monthly",
        period_key="2026-04",
    )

    assert weekly_json == reports / "operator_summary" / "weekly" / "2026-W18" / "weekly_summary.json"
    assert weekly_md == reports / "operator_summary" / "weekly" / "2026-W18" / "weekly_summary.md"
    assert weekly["metrics"]["trade_count"] == 2
    assert weekly["metrics"]["win_count"] == 1
    assert weekly["metrics"]["loss_count"] == 1
    assert weekly["patterns"]["top_exit_pattern_types"][0]["name"] == "peak_drawdown"
    assert monthly_json == reports / "operator_summary" / "monthly" / "2026-04" / "monthly_summary.json"
    assert monthly_md == reports / "operator_summary" / "monthly" / "2026-04" / "monthly_summary.md"
    assert monthly["metrics"]["trade_count"] == 2
    assert "Weekly Summary (2026-W18)" in weekly_md.read_text(encoding="utf-8")
    assert "Monthly Summary (2026-04)" in monthly_md.read_text(encoding="utf-8")


def test_operator_daily_and_symbol_summary_artifacts_are_saved(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    trade_rows = [
        {
            "trade_id": "TRD_20260428_005930_01",
            "date": "2026-04-28",
            "symbol": "005930",
            "status": "closed",
            "entry_reason": "breakout_above_recent_high",
            "exit_reason": "SELL was triggered because peak_drawdown.",
            "entry_pattern_type": "breakout",
            "exit_pattern_type": "peak_drawdown",
            "result_pct": -0.5,
            "hold_seconds": 300,
        }
    ]
    _write_json(reports / "operator_summary" / "symbols" / "005930" / "trade_history.json", trade_rows)
    daily_md, daily_json, daily = generate_operator_daily_summary_artifact(
        reports_root=reports,
        day="2026-04-28",
        daily_report_payload={"events": 12, "approvals": 1, "blocks": 2, "symbols_observed": ["005930"]},
    )
    symbol_md, symbol_json, symbol = generate_operator_symbol_summary_artifact(
        reports_root=reports,
        symbol="005930",
        symbol_trade_report_payload={"symbol": "005930", "history_index": trade_rows},
        symbol_memory_payload={"trade_stats": {"trade_count": 1}},
    )

    assert daily_json == reports / "operator_summary" / "daily" / "2026-04-28" / "daily_summary.json"
    assert daily_md == reports / "operator_summary" / "daily" / "2026-04-28" / "daily_summary.md"
    assert daily["metrics"]["trade_count"] == 1
    assert daily["runtime_activity"]["events"] == 12
    assert symbol_json == reports / "operator_summary" / "symbols" / "005930" / "symbol_summary.json"
    assert symbol_md == reports / "operator_summary" / "symbols" / "005930" / "symbol_summary.md"
    assert symbol["metrics"]["loss_count"] == 1


def test_operator_daily_summary_syncs_strategy_memory_artifacts(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    day = "2026-04-28"
    trade_id = "TRD_20260428_005930_01"
    _write_json(
        reports / "trades" / day / trade_id / "lifecycle_bundle.json",
        {
            "schema_version": "lifecycle_bundle.v1",
            "day": day,
            "trade_id": trade_id,
            "symbol": "005930",
            "lifecycle": {"entry": {"symbol": "005930"}, "exit": {"symbol": "005930"}},
            "strategist_summary": {"playbook": "defensive", "market_regime": "neutral"},
            "trade_outcome": {"return_pct": -0.4, "pnl": -400},
            "strategist_feedback_input": {
                "entry_pattern_type": "breakout",
                "exit_pattern_type": "peak_drawdown",
                "entry_reason": "breakout_above_recent_high",
                "exit_reason": "SELL was triggered because peak_drawdown.",
            },
        },
    )
    _write_json(
        reports / "operator_summary" / "symbols" / "005930" / "trade_history.json",
        [
            {
                "trade_id": trade_id,
                "date": day,
                "symbol": "005930",
                "status": "closed",
                "entry_reason": "breakout_above_recent_high",
                "exit_reason": "SELL was triggered because peak_drawdown.",
                "entry_pattern_type": "breakout",
                "exit_pattern_type": "peak_drawdown",
                "result_pct": -0.4,
                "hold_seconds": 300,
            }
        ],
    )

    _md, _json, payload = generate_operator_daily_summary_artifact(
        reports_root=reports,
        day=day,
        daily_report_payload={"events": 10, "approvals": 1, "blocks": 0},
    )

    sync = payload["performance_memory_sync"]
    assert sync["status"] == "ok"
    assert sync["total_trades"] == 1
    assert reports.joinpath("performance", day, "summary.json").exists()
    assert reports.joinpath("performance", day, "playbook_stats.json").exists()
    memory_path = reports / "performance" / day / "strategy_memory.json"
    assert memory_path.exists()
    memory = json.loads(memory_path.read_text(encoding="utf-8"))
    assert memory["day"] == day
    assert memory["status"] == "ok"
    assert memory["worst_playbooks"] == ["defensive"]
    assert "entry_exit:breakout->peak_drawdown" in (
        memory.get("pattern_performance_snapshot", {}).get("problem_patterns") or []
    )
