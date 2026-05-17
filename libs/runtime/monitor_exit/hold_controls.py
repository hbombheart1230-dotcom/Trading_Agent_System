from __future__ import annotations

import os
from typing import Any, Dict


def _is_trueish(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _nested_dict(parent: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = parent.get(key)
    return value if isinstance(value, dict) else {}


def resolve_min_hold_sec(state: Dict[str, Any], policy: Dict[str, Any]) -> int:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    applied_monitor = _nested_dict(applied_policy, "monitor")
    policy_monitor = _nested_dict(policy, "monitor") if isinstance(policy, dict) else {}

    raw = _nested_dict(applied_monitor, "hold").get("min_hold_seconds")
    if raw is None:
        raw = _nested_dict(policy_monitor, "hold").get("min_hold_seconds")
    if raw is None and isinstance(policy, dict):
        raw = policy.get("min_hold_seconds")
    if raw is None:
        raw = 600
    try:
        return max(0, int(float(raw)))
    except Exception:
        return 600


def resolve_sell_cooldown_sec(state: Dict[str, Any], policy: Dict[str, Any]) -> int:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    applied_execution = _nested_dict(applied_policy, "execution")
    policy_execution = _nested_dict(policy, "execution") if isinstance(policy, dict) else {}

    raw = _nested_dict(applied_execution, "cooldowns").get("sell_sec")
    if raw is None:
        raw = _nested_dict(policy_execution, "cooldowns").get("sell_sec")
    if raw is None and isinstance(policy, dict):
        raw = policy.get("sell_cooldown_sec")
    if raw is None and isinstance(policy, dict):
        raw = policy.get("sell_cooldown_seconds")
    if raw in (None, ""):
        raw = 300
    try:
        return max(0, int(float(raw)))
    except Exception:
        return 300


def resolve_exit_confirm_ticks(state: Dict[str, Any], policy: Dict[str, Any]) -> int:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    applied_monitor = _nested_dict(applied_policy, "monitor")
    policy_monitor = _nested_dict(policy, "monitor") if isinstance(policy, dict) else {}

    raw = _nested_dict(applied_monitor, "exit").get("confirm_ticks")
    if raw is None:
        raw = _nested_dict(policy_monitor, "exit").get("confirm_ticks")
    if raw is None and isinstance(policy, dict):
        raw = policy.get("exit_confirm_ticks")
    if raw is None:
        raw = 2
    try:
        return max(1, int(float(raw)))
    except Exception:
        return 2


def resolve_use_exit_policy(state: Dict[str, Any], policy: Dict[str, Any]) -> bool:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    applied_monitor = _nested_dict(applied_policy, "monitor")
    applied_exit = _nested_dict(applied_monitor, "exit").get("enabled")
    if applied_exit is not None:
        return _is_trueish(applied_exit)
    if state.get("use_exit_policy") is not None:
        return _is_trueish(state.get("use_exit_policy"))
    if isinstance(policy, dict) and policy.get("use_exit_policy") is not None:
        return _is_trueish(policy.get("use_exit_policy"))
    raw_env = str(os.getenv("USE_EXIT_POLICY", "") or "").strip()
    if raw_env:
        return _is_trueish(raw_env)
    return True


def resolve_post_exit_cooldown_sec(
    state: Dict[str, Any],
    policy: Dict[str, Any],
    monitor_policy: Dict[str, Any],
) -> int:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    applied_execution = _nested_dict(applied_policy, "execution")
    policy_execution = _nested_dict(policy, "execution") if isinstance(policy, dict) else {}

    raw = _nested_dict(applied_execution, "cooldowns").get("post_exit_sec")
    if raw in (None, ""):
        raw = state.get("post_exit_cooldown_sec")
    if raw in (None, "") and isinstance(monitor_policy, dict):
        raw = monitor_policy.get("post_exit_cooldown_sec")
    if raw in (None, ""):
        raw = _nested_dict(policy_execution, "cooldowns").get("post_exit_sec")
    if raw in (None, "") and isinstance(policy, dict):
        raw = policy.get("post_exit_cooldown_sec")
    if raw in (None, ""):
        raw = 180
    try:
        return max(0, int(float(raw)))
    except Exception:
        return 180
