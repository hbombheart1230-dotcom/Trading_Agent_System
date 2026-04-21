from __future__ import annotations

from importlib import import_module
from typing import Dict, List


_IMPLEMENTATION_TARGETS: Dict[str, str] = {
    "m13_live_loop": "scripts.run_m13_live_loop:main",
    "live_session_watch": "scripts.run_live_session_watch:main",
    "mock_exam_day": "scripts.run_mock_exam_day:main",
    "commander_runtime_once": "scripts.run_commander_runtime_once:main",
    "m31_agent_chain_probe": "scripts.run_m31_agent_chain_probe:main",
    "offhours_validation_loop": "scripts.run_offhours_validation_loop:main",
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
