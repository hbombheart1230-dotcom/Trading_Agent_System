from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.evaluation.attribution_score_window import build_attribution_score_window


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _daily_score(day: str, *, valid: bool, exit_score: int | None, entry_score: int | None) -> dict:
    return {
        "day": day,
        "counts_as_valid_day": valid,
        "scores": {
            "selection_integrity_score": {"status": "OK", "score": 100, "reasons": []},
            "scanner_alignment_score": {"status": "OK", "score": 80, "reasons": ["scanner_reason"]},
            "entry_timing_score": (
                {"status": "INSUFFICIENT_EVIDENCE", "score": None, "reasons": ["missing"]}
                if entry_score is None
                else {"status": "OK", "score": entry_score, "reasons": ["entry_reason"]}
            ),
            "exit_horizon_score": (
                {"status": "INSUFFICIENT_EVIDENCE", "score": None, "reasons": ["missing"]}
                if exit_score is None
                else {"status": "OK", "score": exit_score, "reasons": ["exit_reason"]}
            ),
            "evidence_quality_score": {"status": "OK", "score": 100, "reasons": []},
        },
        "weakest_observed_axis": {
            "name": "exit_horizon_score" if exit_score is not None else "scanner_alignment_score",
            "score": exit_score if exit_score is not None else 80,
        },
    }


def test_attribution_score_window_aggregates_valid_days_only(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    window_id = "test_window"
    _write(
        reports / "evaluation" / "freeze_window" / window_id / "daily_ledger.json",
        {
            "days": [
                {"day": "2026-06-29", "counts_as_valid_day": False},
                {"day": "2026-06-30", "counts_as_valid_day": True},
                {"day": "2026-07-01", "counts_as_valid_day": True},
            ]
        },
    )
    for day, payload in [
        ("2026-06-29", _daily_score("2026-06-29", valid=False, exit_score=10, entry_score=10)),
        ("2026-06-30", _daily_score("2026-06-30", valid=True, exit_score=50, entry_score=100)),
        ("2026-07-01", _daily_score("2026-07-01", valid=True, exit_score=None, entry_score=80)),
    ]:
        _write(reports / "evaluation" / "daily" / day / "attribution_score_v0.json", payload)
        _write(
            reports / "evaluation" / "daily" / day / "daily_scorecard.json",
            {"artifact_integrity": {"trade_count": 1}},
        )

    result = build_attribution_score_window(reports_root=reports, window_id=window_id)

    assert result["valid_day_count"] == 2
    assert result["axis_summary"]["exit_horizon_score"]["average_score"] == 50
    assert result["axis_summary"]["exit_horizon_score"]["insufficient_day_count"] == 1
    assert result["weakest_axis_distribution"]["exit_horizon_score"] == 1
    assert "2026-06-29" == result["daily_rows"][0]["day"]
    assert result["daily_rows"][0]["valid"] is False
