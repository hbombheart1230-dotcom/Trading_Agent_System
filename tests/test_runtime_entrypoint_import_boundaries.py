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


def test_runtime_entrypoint_scripts_do_not_import_other_scripts() -> None:
    for path in TARGETS:
        text = path.read_text(encoding="utf-8")
        assert "from scripts." not in text, path.as_posix()
        assert "import scripts." not in text, path.as_posix()
