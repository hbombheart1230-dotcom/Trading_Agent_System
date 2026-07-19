from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.evaluation.attribution_score_range import build_attribution_score_range


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _score(day: str, *, scanner: int | None, entry: int) -> dict:
    return {
        "day": day,
        "scores": {
            "selection_integrity_score": {"status": "OK", "score": 100, "reasons": []},
            "scanner_alignment_score": (
                {"status": "INSUFFICIENT_EVIDENCE", "score": None, "reasons": ["missing_scanner"]}
                if scanner is None
                else {"status": "OK", "score": scanner, "reasons": ["scanner_weak"]}
            ),
            "entry_timing_score": {"status": "OK", "score": entry, "reasons": ["entry_ok"]},
            "exit_horizon_score": {"status": "OK", "score": 70, "reasons": []},
            "evidence_quality_score": {"status": "OK", "score": 90, "reasons": []},
        },
        "weakest_observed_axis": {"name": "scanner_alignment_score", "score": scanner},
    }


def test_attribution_score_range_aggregates_available_scored_days(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    _write(reports / "trades" / "2026-06-01" / "TRD_A" / "x.json", {})
    _write(reports / "trades" / "2026-06-02" / "TRD_B" / "x.json", {})
    _write(reports / "evaluation" / "daily" / "2026-06-01" / "attribution_score_v0.json", _score("2026-06-01", scanner=20, entry=80))
    _write(reports / "evaluation" / "daily" / "2026-06-01" / "daily_scorecard.json", {"artifact_integrity": {"trade_count": 1}})
    _write(reports / "evaluation" / "daily" / "2026-06-02" / "attribution_score_v0.json", _score("2026-06-02", scanner=None, entry=100))
    _write(reports / "evaluation" / "daily" / "2026-06-02" / "daily_scorecard.json", {"artifact_integrity": {"trade_count": 1}})

    result = build_attribution_score_range(reports_root=reports, start="2026-06-01", end="2026-06-03")

    assert result["day_count"] == 2
    assert result["available_day_count"] == 2
    assert result["scored_day_count"] == 2
    assert result["total_trade_count"] == 2
    assert result["axis_summary"]["scanner_alignment_score"]["average_score"] == 20
    assert result["axis_summary"]["scanner_alignment_score"]["insufficient_day_count"] == 1
    assert result["weakest_axis_distribution"]["scanner_alignment_score"] == 2


def test_attribution_score_range_can_include_empty_missing_days(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    result = build_attribution_score_range(
        reports_root=reports,
        start="2026-06-01",
        end="2026-06-02",
        include_empty_days=True,
    )

    assert result["day_count"] == 2
    assert result["available_day_count"] == 0
    assert result["axis_summary"]["entry_timing_score"]["missing_day_count"] == 2
