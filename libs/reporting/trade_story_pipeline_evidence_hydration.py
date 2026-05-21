from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def safe_read_json_file(path_value: Any) -> Dict[str, Any]:
    path_text = str(path_value or "").strip()
    if not path_text:
        return {}
    try:
        path = Path(path_text)
        if not path.exists() or not path.is_file():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def hydrate_canonical_agent_artifacts(
    bundle_out: Dict[str, Any],
    canonical_agent_artifacts: Dict[str, Any] | None,
    *,
    read_json_file=safe_read_json_file,
) -> Dict[str, Any]:
    hydrated = dict(canonical_agent_artifacts or {})
    artifacts = bundle_out.get("artifacts") if isinstance(bundle_out.get("artifacts"), dict) else {}
    for agent in ("commander", "strategist", "scanner", "monitor", "supervisor", "executor"):
        if isinstance(hydrated.get(agent), dict) and hydrated.get(agent):
            continue
        path_key = f"canonical_{agent}_json"
        payload = read_json_file(artifacts.get(path_key))
        if payload:
            hydrated[agent] = payload
            hydrated[path_key] = str(artifacts.get(path_key) or "")
    return hydrated


def resolve_selection_monitor_artifact(
    bundle_out: Dict[str, Any],
    canonical_agent_artifacts: Dict[str, Any] | None,
    *,
    read_json_file=safe_read_json_file,
) -> Dict[str, Any]:
    hydrated = dict(canonical_agent_artifacts or {})
    monitor_payload = (
        hydrated.get("monitor")
        if isinstance(hydrated.get("monitor"), dict)
        else bundle_out.get("monitor")
        if isinstance(bundle_out.get("monitor"), dict)
        else {}
    )
    scanner_path = str(
        hydrated.get("canonical_scanner_json")
        or ((bundle_out.get("artifacts") or {}).get("canonical_scanner_json"))
        or ""
    ).strip()
    if scanner_path:
        sibling_monitor = read_json_file(Path(scanner_path).with_name("monitor.json"))
        sibling_handoff = sibling_monitor.get("scanner_monitor_handoff") if isinstance(sibling_monitor.get("scanner_monitor_handoff"), dict) else {}
        sibling_cascade = sibling_handoff.get("entry_candidate_cascade") if isinstance(sibling_handoff.get("entry_candidate_cascade"), dict) else {}
        if (
            sibling_handoff.get("scanner_selected_symbol")
            or sibling_handoff.get("monitor_selected_symbol")
            or sibling_cascade.get("attempted")
            or sibling_cascade.get("fallback_used")
        ):
            return sibling_monitor

    handoff = monitor_payload.get("scanner_monitor_handoff") if isinstance(monitor_payload.get("scanner_monitor_handoff"), dict) else {}
    cascade = handoff.get("entry_candidate_cascade") if isinstance(handoff.get("entry_candidate_cascade"), dict) else {}
    if (
        handoff.get("scanner_selected_symbol")
        or handoff.get("monitor_selected_symbol")
        or cascade.get("attempted")
        or cascade.get("fallback_used")
    ):
        return dict(monitor_payload)

    return dict(monitor_payload)
