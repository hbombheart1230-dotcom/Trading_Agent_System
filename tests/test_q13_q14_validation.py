from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.evaluation.q13_q14_validation import build_q13_q14_validation_report


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _q13() -> dict:
    return {
        "scores": {
            "selection_integrity_score": {"status": "OK", "score": 95},
            "scanner_alignment_score": {"status": "OK", "score": 70},
            "entry_timing_score": {"status": "INSUFFICIENT_EVIDENCE", "score": None},
            "exit_horizon_score": {"status": "OK", "score": 80},
            "evidence_quality_score": {"status": "OK", "score": 95},
        }
    }


def _q14(largest: str, missing: int = 0) -> dict:
    causes = {
        "Scanner Ranking Failure": 1 if largest == "Scanner Ranking Failure" else 0,
        "Candidate Filtering": 1 if largest == "Candidate Filtering" else 0,
        "Strategist Override": 1 if largest == "Strategist Override" else 0,
        "Missing Evidence": missing,
    }
    return {
        "trade_count": sum(causes.values()) or 1,
        "largest_behavior_root_cause": {"root_cause": largest},
        "cause_summary": [
            {"root_cause": cause, "trade_count": count}
            for cause, count in causes.items()
        ],
    }


def _horizon(exit_count: int = 0) -> dict:
    return {
        "rows": [
            {"horizon_violation_candidate": True}
            for _ in range(exit_count)
        ]
    }


def _seed_day(root: Path, day: str, *, largest: str, missing: int = 0, exit_count: int = 0) -> None:
    daily = root / "reports" / "evaluation" / "daily" / day
    _write(daily / "attribution_score_v0.json", _q13())
    _write(daily / "scanner_alignment_root_cause_report.json", _q14(largest, missing=missing))
    _write(daily / "horizon_compliance_report.json", _horizon(exit_count=exit_count))


def test_q13_q14_validation_go_when_scanner_failure_is_stable(tmp_path: Path) -> None:
    days = [f"2026-07-0{i}" for i in range(1, 6)]
    for index, day in enumerate(days):
        _seed_day(
            tmp_path,
            day,
            largest="Scanner Ranking Failure" if index < 4 else "Candidate Filtering",
        )

    result = build_q13_q14_validation_report(reports_root=tmp_path / "reports", days=days)

    assert result["decision"] == "GO"
    assert result["largest_behavior_root_cause_day_counts"]["Scanner Ranking Failure"] == 4
    assert result["decision_scope"] == "diagnostic_stability_only"
    assert result["behavior_patch_authorized"] is False


def test_q13_q14_validation_no_go_when_missing_evidence_is_high(tmp_path: Path) -> None:
    days = [f"2026-07-0{i}" for i in range(1, 6)]
    for day in days:
        _seed_day(tmp_path, day, largest="Scanner Ranking Failure", missing=2)

    result = build_q13_q14_validation_report(reports_root=tmp_path / "reports", days=days)

    assert result["decision"] == "NO_GO"
    assert "missing_evidence_above_threshold" in result["decision_reasons"]


def test_q13_q14_validation_in_progress_before_five_days(tmp_path: Path) -> None:
    days = ["2026-07-01", "2026-07-02"]
    for day in days:
        _seed_day(tmp_path, day, largest="Scanner Ranking Failure")

    result = build_q13_q14_validation_report(reports_root=tmp_path / "reports", days=days)

    assert result["decision"] == "IN_PROGRESS"
    assert result["day_count"] == 2
