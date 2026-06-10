from __future__ import annotations

import os
from typing import Any, Dict, Optional

from libs.runtime.commander.policy_surface import COMMANDER_TEMPORARY_RUNTIME_ENV_DEFAULTS


def is_trueish(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def env_bool(name: str, default: bool) -> bool:
    raw = str(os.getenv(name, "") or "").strip().lower()
    if not raw:
        return bool(default)
    return raw in {"1", "true", "yes", "y", "on"}


def commander_default_bool(name: str, default: bool) -> bool:
    raw = str(COMMANDER_TEMPORARY_RUNTIME_ENV_DEFAULTS.get(name, "") or "").strip()
    if raw:
        return is_trueish(raw)
    return bool(default)


def apply_commander_temporary_runtime_defaults(state: Dict[str, Any]) -> Dict[str, Optional[str]]:
    previous = {key: os.environ.get(key) for key in COMMANDER_TEMPORARY_RUNTIME_ENV_DEFAULTS}
    for key, value in COMMANDER_TEMPORARY_RUNTIME_ENV_DEFAULTS.items():
        if os.environ.get(key) in (None, ""):
            os.environ[key] = str(value)

    policy = dict(state.get("policy") or {}) if isinstance(state.get("policy"), dict) else {}
    policy.setdefault("use_strategy_memory_feedback", env_bool("USE_STRATEGY_MEMORY_FEEDBACK", True))
    policy.setdefault("use_strategy_performance_memory", env_bool("USE_STRATEGY_PERFORMANCE_MEMORY", True))
    state["policy"] = policy
    state.setdefault("commander_post_scanner_refresh_enabled", env_bool("COMMANDER_POST_SCANNER_REFRESH_ENABLED", True))
    state.setdefault("memory_bias_observation_only", env_bool("MEMORY_BIAS_OBSERVATION_ONLY", True))
    state.setdefault("commander_memory_bias_observation_only", env_bool("MEMORY_BIAS_OBSERVATION_ONLY", True))
    state.setdefault("commander_memory_usage_disabled", env_bool("COMMANDER_MEMORY_USAGE_DISABLED", False))
    state.setdefault("strategist_memory_usage_disabled", env_bool("STRATEGIST_MEMORY_USAGE_DISABLED", False))
    state.setdefault("strategy_memory_persist_enabled", env_bool("STRATEGY_MEMORY_PERSIST_ENABLED", True))
    state["commander_temporary_runtime_defaults"] = {
        "source": "commander_runtime_code_default",
        "values": dict(COMMANDER_TEMPORARY_RUNTIME_ENV_DEFAULTS),
        "env_transport": True,
    }
    return previous


def restore_commander_temporary_runtime_env(previous: Dict[str, Optional[str]]) -> None:
    for key, value in dict(previous or {}).items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def commander_post_scanner_refresh_enabled(state: Dict[str, Any]) -> bool:
    if isinstance(state, dict) and state.get("commander_post_scanner_refresh_enabled") not in (None, ""):
        return is_trueish(state.get("commander_post_scanner_refresh_enabled"))
    return env_bool(
        "COMMANDER_POST_SCANNER_REFRESH_ENABLED",
        commander_default_bool("COMMANDER_POST_SCANNER_REFRESH_ENABLED", True),
    )


def commander_pre_entry_exit_sweep_enabled(state: Dict[str, Any]) -> bool:
    if isinstance(state, dict):
        if state.get("commander_pre_entry_exit_sweep_enabled") not in (None, ""):
            return is_trueish(state.get("commander_pre_entry_exit_sweep_enabled"))
        applied = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
        commander = applied.get("commander") if isinstance(applied.get("commander"), dict) else {}
        route = commander.get("route") if isinstance(commander.get("route"), dict) else {}
        if route.get("pre_entry_exit_sweep_enabled") not in (None, ""):
            return is_trueish(route.get("pre_entry_exit_sweep_enabled"))
    return env_bool("COMMANDER_PRE_ENTRY_EXIT_SWEEP_ENABLED", True)


def commander_memory_usage_disabled(state: Dict[str, Any]) -> bool:
    if isinstance(state, dict):
        if state.get("commander_memory_usage_disabled") not in (None, ""):
            return is_trueish(state.get("commander_memory_usage_disabled"))
        applied = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
        commander = applied.get("commander") if isinstance(applied.get("commander"), dict) else {}
        memory_usage = commander.get("memory_usage") if isinstance(commander.get("memory_usage"), dict) else {}
        if memory_usage.get("disabled") not in (None, ""):
            return is_trueish(memory_usage.get("disabled"))
    return env_bool(
        "COMMANDER_MEMORY_USAGE_DISABLED",
        commander_default_bool("COMMANDER_MEMORY_USAGE_DISABLED", False),
    )
