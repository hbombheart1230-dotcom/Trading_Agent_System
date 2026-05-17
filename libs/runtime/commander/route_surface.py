from __future__ import annotations

from typing import Any, Dict

from libs.runtime.commander.env_overrides import is_trueish


def derive_commander_selected_route(state: Dict[str, Any]) -> str:
    status_text = str(state.get("runtime_status") or "").strip()
    path_text = str(state.get("path") or "").strip()
    phase_text = str(state.get("runtime_phase") or "").strip()
    if "monitor_only" in path_text:
        return "monitor_only"
    if "cached" in path_text:
        return "cached_strategist"
    if phase_text == "preopen" or "preopen" in path_text:
        return "preopen"
    if phase_text == "closeout" or "closeout" in path_text:
        return "closeout"
    if "blocked" in path_text or status_text in {"blocked", "preflight_blocked"}:
        return "blocked"
    if status_text in {"error", "cooldown_wait", "degraded"}:
        return "degraded"
    return "full_cycle"


def normalize_reporter_integration_config(state: Dict[str, Any]) -> Dict[str, Any]:
    config = state.get("reporter_integration") if isinstance(state.get("reporter_integration"), dict) else {}
    hooks = config.get("hooks") if isinstance(config.get("hooks"), dict) else {}
    return {
        "enabled": is_trueish(config.get("enabled")),
        "emit_reports": is_trueish(config.get("emit_reports")),
        "hooks": dict(hooks),
        "event_log_path": str(config.get("event_log_path") or state.get("event_log_path") or "data/logs/events.jsonl"),
        "reports_root": str(config.get("reports_root") or state.get("reports_root") or "reports"),
        "day": str(config.get("day") or state.get("day") or ""),
    }


def reporter_hook_requested(config: Dict[str, Any], hook_name: str, *, default: bool = False) -> bool:
    hooks = config.get("hooks") if isinstance(config.get("hooks"), dict) else {}
    if hook_name in hooks:
        return is_trueish(hooks.get(hook_name))
    direct_key = f"{hook_name}_enabled"
    if direct_key in config:
        return is_trueish(config.get(direct_key))
    return bool(default)


def resolve_commander_reporter_feedback_policy(
    state: Dict[str, Any],
    *,
    selected_route: str = "",
    phase: str = "",
) -> Dict[str, Any]:
    route = str(selected_route or derive_commander_selected_route(state) or "").strip().lower()
    phase_text = str(phase or state.get("runtime_phase") or "session").strip().lower() or "session"

    if phase_text == "closeout":
        mode = "enabled"
        reason = "closeout_report_heavy"
    elif route == "monitor_only":
        mode = "disabled"
        reason = "monitor_only_route"
    elif route == "cached_strategist":
        mode = "disabled"
        reason = "cached_strategist_route"
    elif route == "full_cycle":
        mode = "auto"
        reason = "full_cycle_route"
    else:
        mode = "auto"
        reason = f"{phase_text}_default_auto"

    return {
        "reporter_feedback_mode": mode,
        "reporter_feedback_mode_source": "commander_applied_policy",
        "reporter_feedback_mode_reason": reason,
        "reporter_feedback_semantics": "advisory_only",
        "selected_route": route or "unknown",
        "runtime_phase": phase_text,
    }
