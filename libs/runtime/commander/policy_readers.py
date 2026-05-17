from __future__ import annotations

import os
from typing import Any, Dict

from libs.runtime.commander.env_overrides import is_trueish


def coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def merge_nested_policy_dict(base: Dict[str, Any], updates: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(base or {})
    for key, value in dict(updates or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = merge_nested_policy_dict(dict(out.get(key) or {}), value)
        else:
            out[key] = value
    return out


def nested_policy_value(policy: Dict[str, Any], *path: str) -> Any:
    cursor: Any = policy
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    return cursor


def commander_trade_report_enabled(state: Dict[str, Any]) -> bool:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    enabled = nested_policy_value(applied_policy, "reporter", "trade_report", "enabled")
    if enabled is None:
        return False
    return bool(enabled)


def resolve_commander_route_toggle(
    state: Dict[str, Any],
    *,
    nested_path: tuple[str, ...],
    state_key: str,
    default: bool,
) -> tuple[bool, str]:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    cursor = nested_policy_value(applied_policy, *nested_path)
    if cursor is not None:
        return is_trueish(cursor), "commander_applied_policy"
    if state.get(state_key) is not None:
        return is_trueish(state.get(state_key)), "state_fallback"
    return bool(default), "default"


def resolve_commander_cooldown_policy(state: Dict[str, Any]) -> tuple[int, int]:
    policy = state.get("resilience_policy") if isinstance(state.get("resilience_policy"), dict) else {}
    threshold_default = coerce_int(os.getenv("COMMANDER_INCIDENT_THRESHOLD", "0"), 0)
    cooldown_default = coerce_int(os.getenv("COMMANDER_COOLDOWN_SEC", "0"), 0)
    threshold = coerce_int(policy.get("incident_threshold"), threshold_default)
    cooldown_sec = coerce_int(policy.get("cooldown_sec"), cooldown_default)
    return max(0, threshold), max(0, cooldown_sec)
