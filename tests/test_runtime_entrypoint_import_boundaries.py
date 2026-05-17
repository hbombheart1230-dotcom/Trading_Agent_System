from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / "scripts" / "run_session.py",
    ROOT / "scripts" / "run_m13_live_loop.py",
    ROOT / "scripts" / "run_live_session_watch.py",
    ROOT / "scripts" / "run_mock_exam_day.py",
    ROOT / "scripts" / "run_offhours_validation_loop.py",
]
LIBRARY_BOUNDARY_TARGETS = [
    ROOT / "libs" / "reporting" / "daily_report.py",
    ROOT / "libs" / "reporting" / "daily_report_generator.py",
    ROOT / "libs" / "reporting" / "metrics_report_generator.py",
    ROOT / "libs" / "reporting" / "operator_visibility.py",
    ROOT / "libs" / "reporting" / "reporter_feedback.py",
    ROOT / "libs" / "reporting" / "report_source_helpers.py",
    ROOT / "libs" / "read" / "kiwoom_broker_truth_common.py",
]


def test_runtime_entrypoint_scripts_do_not_import_other_scripts() -> None:
    for path in TARGETS:
        text = path.read_text(encoding="utf-8")
        assert "from scripts." not in text, path.as_posix()
        assert "import scripts." not in text, path.as_posix()


def test_runtime_report_source_helpers_do_not_import_scripts() -> None:
    for path in LIBRARY_BOUNDARY_TARGETS:
        text = path.read_text(encoding="utf-8")
        assert "from scripts." not in text, path.as_posix()
        assert "import scripts." not in text, path.as_posix()
