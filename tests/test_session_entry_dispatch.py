from __future__ import annotations

import pytest

from libs.runtime.session_entry_dispatch import resolve_entry_implementation_path


def test_resolve_entry_implementation_path_returns_script_main_target() -> None:
    assert resolve_entry_implementation_path("m13_live_loop") == "scripts.run_m13_live_loop:main"
    assert resolve_entry_implementation_path("mock_exam_day") == "scripts.run_mock_exam_day:main"


def test_resolve_entry_implementation_path_rejects_unknown_id() -> None:
    with pytest.raises(SystemExit):
        resolve_entry_implementation_path("missing")
