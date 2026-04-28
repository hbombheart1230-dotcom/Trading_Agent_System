from __future__ import annotations

import json
from pathlib import Path

from libs.reporting.report_maintenance import ArchiveCandidate
from libs.reporting.report_maintenance import apply_archive_candidates
from libs.reporting.report_maintenance import build_report_inventory


def test_report_inventory_detects_offhours_and_legacy_daily(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "offhours_full_trace_demo").mkdir()
    (reports / "offhours_full_trace_demo" / "demo.md").write_text("x", encoding="utf-8")
    (reports / "operator_summary" / "daily" / "2026-03-13").mkdir(parents=True)
    (reports / "operator_summary" / "daily" / "2026-03-13" / "daily_report.md").write_text("canonical", encoding="utf-8")
    (reports / "operator_summary" / "daily" / "2026-03-13" / "daily_report.json").write_text("{}", encoding="utf-8")
    (reports / "daily_report_2026-03-13.md").write_text("legacy", encoding="utf-8")
    (reports / "daily_report_2026-03-13.json").write_text("{}", encoding="utf-8")
    (reports / "daily_2026-03-13.md").write_text("legacy canonical-name-in-root", encoding="utf-8")
    (reports / "daily_2026-03-13.json").write_text("{}", encoding="utf-8")

    inv = build_report_inventory(reports, event_log_path=tmp_path / "missing_events.jsonl")
    candidates = inv.get("archive_candidates") or []
    rel_paths = {item["rel_path"] for item in candidates}
    assert "offhours_full_trace_demo" in rel_paths
    assert "daily_report_2026-03-13.md" in rel_paths
    assert "daily_report_2026-03-13.json" in rel_paths
    assert "daily_2026-03-13.md" in rel_paths
    assert "daily_2026-03-13.json" in rel_paths


def test_report_inventory_warns_when_operator_summary_uses_missing_event_path(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    op = reports / "operator_summary" / "daily" / "2026-03-13"
    op.mkdir(parents=True)
    payload = {
        "day": "2026-03-13",
        "inputs": {"event_log_path": "data/events.jsonl"},
        "trading_activity_summary": {"run_total": 0},
    }
    (op / "operator_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False),
        encoding="utf-8",
    )
    event_log_path = tmp_path / "data" / "logs" / "events.jsonl"
    event_log_path.parent.mkdir(parents=True)
    event_log_path.write_text('{"ts":"2026-03-13T05:00:00+00:00","run_id":"r1"}\n', encoding="utf-8")

    inv = build_report_inventory(reports, event_log_path=event_log_path)
    warning_types = {item["type"] for item in inv.get("warnings") or []}
    assert "operator_summary_input_path_missing" in warning_types
    assert "operator_summary_zero_runs" in warning_types


def test_apply_archive_candidates_moves_directory(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    src = reports / "offhours_mode_clarity_check"
    src.mkdir()
    (src / "sample.md").write_text("x", encoding="utf-8")

    moved = apply_archive_candidates(
        reports,
        [
            ArchiveCandidate(
                rel_path="offhours_mode_clarity_check",
                reason="test",
                category="offhours_experiments",
            )
        ],
    )
    assert len(moved) == 1
    assert not src.exists()
    assert (reports / "archive" / "experiments" / "offhours" / "offhours_mode_clarity_check" / "sample.md").exists()


def test_report_inventory_detects_legacy_milestone_dirs(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "m22_closeout").mkdir()
    (reports / "m22_closeout" / "metrics_2026-02-17.json").write_text("{}", encoding="utf-8")

    inv = build_report_inventory(reports, event_log_path=tmp_path / "missing_events.jsonl")
    candidates = inv.get("archive_candidates") or []
    item = next((x for x in candidates if x["rel_path"] == "m22_closeout"), None)
    assert item is not None
    assert item["category"] == "legacy_milestone_dir"
    assert item["archive_target"] == str(Path("archive") / "milestones" / "m22_closeout")


def test_report_inventory_warns_on_misplaced_trade_day_root(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    reports.mkdir()
    misplaced = tmp_path / "2026-03-19" / "TRD_20260319_000660_01"
    misplaced.mkdir(parents=True)

    inv = build_report_inventory(reports, event_log_path=tmp_path / "missing_events.jsonl")

    warning = next((item for item in inv.get("warnings") or [] if item.get("type") == "misplaced_trade_day_root"), None)
    assert warning is not None
    assert warning["path"].endswith(str(Path("2026-03-19")))
