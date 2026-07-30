from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.evaluation.no_trade_attribution import (
    build_no_trade_attribution_report,
    render_no_trade_attribution_report,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_no_trade_attribution_requires_forward_review_for_approve_noop(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write(
        reports / "operator_summary" / "daily" / "2026-07-07" / "q9_decision_windows.json",
        {
            "schema_version": "q9_decision_windows.v1",
            "windows": [
                {
                    "generated_at": "2026-07-07T00:00:00+00:00",
                    "scanner_control": {"top1_symbol": "005930"},
                    "strategist_selection": {"selected_symbol": "005930"},
                    "commander_final": {
                        "decision": "approve",
                        "selected_symbol": "005930",
                        "candidate_symbol": "005930",
                        "monitor_intent": "NOOP",
                        "monitor_reason": "quant_entry_block:cost_edge_fail",
                        "monitor_observation": {
                            "reason": "quant_entry_block:cost_edge_fail",
                        },
                        "reason": "within_policy",
                        "detail": "cost_edge_not_ready",
                    },
                },
                {
                    "generated_at": "2026-07-07T07:00:00+00:00",
                    "scanner_control": {"top1_symbol": "005930"},
                    "commander_final": {
                        "decision": "approve",
                        "selected_symbol": "005930",
                        "monitor_intent": "NOOP",
                        "monitor_reason": "post_close_row_must_be_ignored",
                    },
                },
                {
                    "generated_at": "2026-07-07T01:00:00+00:00",
                    "decision_id": "pytest-synthetic-row",
                    "scanner_control": {"top1_symbol": "AAA"},
                    "commander_final": {
                        "decision": "approve",
                        "selected_symbol": "AAA",
                        "monitor_intent": "NOOP",
                        "monitor_reason": "synthetic_row_must_be_ignored",
                    },
                }
            ],
        },
    )
    _write(
        reports
        / "evaluation"
        / "opportunity_engine_shadow"
        / "2026-07-07"
        / "opportunity_engine_daily_report.json",
        {
            "summary": {
                "virtual_trades": 2,
                "win_rate": 0.5,
                "avg_net_return": -0.1,
                "avg_mfe": 1.2,
                "avg_mae": -0.4,
                "profit_factor": 0.8,
            }
        },
    )

    report = build_no_trade_attribution_report(
        day="2026-07-07",
        reports_root=reports,
        trade_count=0,
    )

    assert report["no_trade_class"] == "FILTERING_REVIEW_REQUIRED"
    assert (
        report["primary_issue"]
        == "commander_approved_monitor_noop_requires_forward_review"
    )
    assert report["commander_approve_monitor_noop_count"] == 1
    assert report["monitor_noop_reasons"] == [
        {"name": "quant_entry_block:cost_edge_fail", "count": 1}
    ]
    assert report["shadow_opportunity_status"] == "MFE_ONLY_SHADOW"
    assert "No-Trade Attribution" in render_no_trade_attribution_report(report)
