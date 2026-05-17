from __future__ import annotations

import pytest

from libs.runtime.session_entry_dispatch import resolve_entry_implementation_path


def test_resolve_entry_implementation_path_prefers_library_entrypoints() -> None:
    assert resolve_entry_implementation_path("live_session_watch") == "libs.runtime.entrypoints.live_session_watch:main"
    assert resolve_entry_implementation_path("commander_runtime_once") == "libs.runtime.entrypoints.commander_runtime_once:main"
    assert resolve_entry_implementation_path("m31_agent_chain_probe") == "libs.runtime.entrypoints.m31_agent_chain_probe:main"
    assert resolve_entry_implementation_path("offhours_validation_loop") == "libs.runtime.entrypoints.offhours_validation_loop:main"
    assert resolve_entry_implementation_path("m13_live_loop") == "libs.runtime.entrypoints.m13_live_loop:main"
    assert resolve_entry_implementation_path("mock_exam_day") == "libs.runtime.entrypoints.mock_exam_day:main"


def test_resolve_entry_implementation_path_rejects_unknown_id() -> None:
    with pytest.raises(SystemExit):
        resolve_entry_implementation_path("missing")
