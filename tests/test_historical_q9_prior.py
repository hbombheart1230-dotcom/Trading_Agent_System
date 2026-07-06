from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.evaluation.historical_prior import (
    iter_historical_trade_dirs,
    render_historical_prior_markdown,
    summarize_historical_prior,
)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_iter_historical_trade_dirs_excludes_freeze_window(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    old_trade = reports / "trades" / "2026-06-20" / "1000" / "TRD_20260620_005930_01"
    freeze_trade = reports / "trades" / "2026-06-30" / "1000" / "TRD_20260630_005930_01"
    _write(old_trade / "lifecycle_bundle.json", {"trade_id": old_trade.name})
    _write(freeze_trade / "lifecycle_bundle.json", {"trade_id": freeze_trade.name})

    rows = iter_historical_trade_dirs(reports, before_day="2026-06-29")

    assert rows == [old_trade]


def test_historical_prior_summary_marks_prior_only_and_counts_metrics() -> None:
    models = [
        {
            "day": "2026-06-20",
            "symbol": "005930",
            "selection": {"selected_rank": 1, "strategist_playbook": "vwap_reclaim_pullback"},
        },
        {
            "day": "2026-06-21",
            "symbol": "000660",
            "selection": {"selected_rank": 4, "strategist_playbook": "vwap_reclaim_pullback"},
        },
    ]
    evaluations = [
        {
            "day": "2026-06-20",
            "symbol": "005930",
            "integrity": {"status": "PASS", "promotion_metric_eligible": True, "watch_items": [], "defects": []},
            "realized_outcome": {"net_return_pct": 0.5},
            "horizon_alignment": {"bucket": "scalp"},
        },
        {
            "day": "2026-06-21",
            "symbol": "000660",
            "integrity": {
                "status": "WATCH",
                "promotion_metric_eligible": True,
                "watch_items": ["sub_60_second_exit"],
                "defects": [],
            },
            "realized_outcome": {"net_return_pct": -1.0},
            "horizon_alignment": {"bucket": "intraday"},
        },
    ]

    summary = summarize_historical_prior(
        models=models,
        evaluations=evaluations,
        attributions=[{"deltas": {}}, {"deltas": {}}],
        errors=[],
        from_day="",
        before_day="2026-06-29",
    )
    markdown = render_historical_prior_markdown(summary)

    assert summary["scope"]["official_q9_freeze_sample"] is False
    assert summary["coverage"]["trade_count"] == 2
    assert summary["performance"]["eligible"]["average_return_pct"] == -0.25
    assert summary["breakdowns"]["selected_rank_bucket"]["rank1"]["count"] == 1
    assert "prior evidence only" in markdown
