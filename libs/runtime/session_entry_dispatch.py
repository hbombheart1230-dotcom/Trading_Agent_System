from __future__ import annotations

from importlib import import_module
from typing import Dict, List


_IMPLEMENTATION_TARGETS: Dict[str, str] = {
    "m13_live_loop": "libs.runtime.entrypoints.m13_live_loop:main",
    "live_session_watch": "libs.runtime.entrypoints.live_session_watch:main",
    "mock_exam_day": "libs.runtime.entrypoints.mock_exam_day:main",
    "commander_runtime_once": "libs.runtime.entrypoints.commander_runtime_once:main",
    "m31_agent_chain_probe": "libs.runtime.entrypoints.m31_agent_chain_probe:main",
    "offhours_validation_loop": "libs.runtime.entrypoints.offhours_validation_loop:main",
}


def resolve_entry_implementation_path(implementation_id: str) -> str:
    key = str(implementation_id or "").strip()
    target = _IMPLEMENTATION_TARGETS.get(key)
    if not target:
        raise SystemExit(f"unsupported implementation_id: {key}")
    return target


def dispatch_entry_implementation(implementation_id: str, argv: List[str]) -> int:
    module_name, attr_name = resolve_entry_implementation_path(implementation_id).split(":", 1)
    module = import_module(module_name)
    main_fn = getattr(module, attr_name)
    return int(main_fn(argv))
