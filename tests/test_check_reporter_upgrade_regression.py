from __future__ import annotations

import json
from pathlib import Path

from scripts.check_reporter_upgrade_regression import analyze_day, compare_days


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_analyze_day_counts_fallback_and_trace_quality(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    day = "2026-04-15"

    trade_a = reports_root / "trades" / day / "TRD_20260415_005930_01"
    _write_json(
        trade_a / "lifecycle_bundle.json",
        {
            "trade_lifecycle_status": "closed",
            "lifecycle": {"exit": {"reason": "take_profit"}},
            "artifacts": {
                "canonical_commander_json": "",
                "canonical_strategist_json": "",
                "canonical_scanner_json": "",
                "canonical_monitor_json": "",
                "canonical_supervisor_json": "",
                "canonical_executor_json": "",
            },
            "scanner_selection_trace": {"ranked_candidates": []},
            "monitor_stop_policy_trace": {},
        },
    )
    _write_json(
        trade_a / "reports" / "ai_trade_report.json",
        {
            "section_provenance": {
                "market_context": {"source": "fallback"},
                "reporter_evaluation": {"source": "fallback"},
                "errors_weaknesses_improvement_points": {"source": "fallback"},
            }
        },
    )

    trade_b = reports_root / "trades" / day / "TRD_20260415_000660_01"
    _write_json(
        trade_b / "lifecycle_bundle.json",
        {
            "trade_lifecycle_status": "open",
            "artifacts": {
                "canonical_commander_json": "x",
                "canonical_strategist_json": "x",
                "canonical_scanner_json": "x",
                "canonical_monitor_json": "x",
                "canonical_supervisor_json": "x",
                "canonical_executor_json": "x",
            },
            "scanner_selection_trace": {"ranked_candidates": [{"symbol": "000660"}]},
            "monitor_stop_policy_trace": {"active_exit_axis": "drawdown"},
        },
    )

    out = analyze_day(reports_root, day)
    assert out["total_trades"] == 2
    assert out["closed_trades"] == 1
    assert out["closed_trade_ai_report_exists"] == 1
    assert out["closed_trade_ai_report_missing"] == 0
    assert out["all_fallback_section_count"] == 1
    assert out["reporter_fallback_count"] == 1
    assert out["missing_canonical_path_count"] == 1
    assert out["thin_trace_count"] == 1


def test_compare_days_returns_delta_map(tmp_path: Path) -> None:
    reports_root = tmp_path / "reports"
    day_a = "2026-04-14"
    day_b = "2026-04-15"

    _write_json(
        reports_root / "trades" / day_a / "TRD_20260414_005930_01" / "lifecycle_bundle.json",
        {"trade_lifecycle_status": "closed", "lifecycle": {"exit": {"reason": "x"}}, "artifacts": {}},
    )
    _write_json(
        reports_root / "trades" / day_b / "TRD_20260415_005930_01" / "lifecycle_bundle.json",
        {"trade_lifecycle_status": "closed", "lifecycle": {"exit": {"reason": "x"}}, "artifacts": {}},
    )
    _write_json(
        reports_root / "trades" / day_b / "TRD_20260415_005930_01" / "reports" / "ai_trade_report.json",
        {"section_provenance": {"market_context": {"source": "canonical"}}},
    )

    base = analyze_day(reports_root, day_a)
    target = analyze_day(reports_root, day_b)
    cmp = compare_days(base, target)
    assert cmp["base_day"] == day_a
    assert cmp["target_day"] == day_b
    assert cmp["deltas"]["closed_trade_ai_report_exists"] == 1
    assert cmp["deltas"]["closed_trade_ai_report_missing"] == -1

