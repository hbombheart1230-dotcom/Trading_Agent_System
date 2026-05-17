from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Dict, Tuple

from libs.runtime.commander.env_overrides import commander_memory_usage_disabled, is_trueish
from libs.runtime.commander.policy_readers import coerce_int, resolve_commander_route_toggle
from libs.runtime.commander_memory_policy import build_commander_memory_policy
from libs.runtime.memory_packet_loader import load_commander_memory_packets


def runtime_now_epoch(state: Dict[str, Any]) -> int:
    explicit_epoch = coerce_int(state.get("now_epoch"), 0)
    if explicit_epoch > 0:
        return explicit_epoch
    raw_ts = str(state.get("ts") or "").strip()
    if raw_ts:
        try:
            stamped = raw_ts[:-1] + "+00:00" if raw_ts.endswith("Z") else raw_ts
            return int(datetime.fromisoformat(stamped).timestamp())
        except Exception:
            pass
    return int(time.time())


def portfolio_open_position_count(state: Dict[str, Any]) -> int:
    snapshot = state.get("portfolio_snapshot") if isinstance(state.get("portfolio_snapshot"), dict) else {}
    positions = snapshot.get("positions")
    if isinstance(positions, dict):
        rows = list(positions.values())
    elif isinstance(positions, list):
        rows = positions
    else:
        rows = []
    count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        if coerce_int(row.get("qty"), 0) > 0:
            count += 1
    return int(count)


def strategist_cache_payload(state: Dict[str, Any]) -> Dict[str, Any]:
    persisted_state = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    raw_cached = (
        persisted_state.get("strategist_output_cache")
        if isinstance(persisted_state.get("strategist_output_cache"), dict)
        else {}
    )
    if isinstance(raw_cached.get("output"), dict):
        return dict(raw_cached)
    if raw_cached:
        return {"output": dict(raw_cached), "generated_epoch": 0, "source": "legacy_cache"}
    return {}


def assess_cached_strategist_memory_context(state: Dict[str, Any], cached_output: Dict[str, Any]) -> Dict[str, Any]:
    output = dict(cached_output or {}) if isinstance(cached_output, dict) else {}
    cached_strategy_policy = (
        dict(output.get("strategy_policy") or {})
        if isinstance(output.get("strategy_policy"), dict)
        else {}
    )
    cached_commander_context = (
        dict(cached_strategy_policy.get("commander_context") or {})
        if isinstance(cached_strategy_policy.get("commander_context"), dict)
        else {}
    )
    cached_policy = (
        dict(output.get("commander_memory_policy") or {})
        if isinstance(output.get("commander_memory_policy"), dict)
        else dict(cached_commander_context.get("commander_memory_policy") or {})
        if isinstance(cached_commander_context.get("commander_memory_policy"), dict)
        else {}
    )
    cached_scanner_summary = (
        dict(output.get("scanner_memory_bias_summary") or {})
        if isinstance(output.get("scanner_memory_bias_summary"), dict)
        else dict(cached_commander_context.get("scanner_memory_bias_summary") or {})
        if isinstance(cached_commander_context.get("scanner_memory_bias_summary"), dict)
        else {}
    )
    cached_monitor_summary = (
        dict(output.get("monitor_memory_bias_summary") or {})
        if isinstance(output.get("monitor_memory_bias_summary"), dict)
        else dict(cached_commander_context.get("monitor_memory_bias_summary") or {})
        if isinstance(cached_commander_context.get("monitor_memory_bias_summary"), dict)
        else {}
    )
    cached_context_available = bool(cached_policy or cached_scanner_summary or cached_monitor_summary)
    current_layers: list[str] = []
    current_scanner_enabled = False
    current_monitor_enabled = False
    try:
        current_packets = load_commander_memory_packets(state=state)
        current_policy = build_commander_memory_policy(
            session_bias=str(
                ((state.get("commander_decision") or {}).get("session_bias"))
                or state.get("session_bias")
                or state.get("runtime_phase")
                or "session"
            ),
            memory_packets=current_packets,
            usage_disabled=commander_memory_usage_disabled(state),
        )
        current_layers = [str(x or "") for x in list(current_policy.get("active_layers") or []) if str(x).strip()][:4]
        current_scanner_enabled = bool(current_policy.get("scanner_bias_enabled"))
        current_monitor_enabled = bool(current_policy.get("monitor_bias_enabled"))
    except Exception:
        pass
    cached_layers = [
        str(x or "")
        for x in list(
            cached_policy.get("active_layers")
            or cached_scanner_summary.get("active_layers")
            or cached_monitor_summary.get("active_layers")
            or []
        )[:4]
        if str(x or "").strip()
    ]
    cached_scanner_enabled = bool(
        cached_scanner_summary.get("enabled")
        if cached_scanner_summary.get("enabled") is not None
        else cached_policy.get("scanner_bias_enabled")
    )
    cached_monitor_enabled = bool(
        cached_monitor_summary.get("enabled")
        if cached_monitor_summary.get("enabled") is not None
        else cached_policy.get("monitor_bias_enabled")
    )
    if not cached_context_available:
        return {
            "mismatch": False,
            "cached_memory_context_available": False,
            "cached_active_layers": list(cached_layers),
            "current_active_layers": list(current_layers),
            "cached_scanner_bias_enabled": False,
            "current_scanner_bias_enabled": bool(current_scanner_enabled),
            "cached_monitor_bias_enabled": False,
            "current_monitor_bias_enabled": bool(current_monitor_enabled),
        }
    mismatch = (
        cached_layers != current_layers
        or cached_scanner_enabled != current_scanner_enabled
        or cached_monitor_enabled != current_monitor_enabled
    )
    return {
        "mismatch": bool(mismatch),
        "cached_memory_context_available": True,
        "cached_active_layers": list(cached_layers),
        "current_active_layers": list(current_layers),
        "cached_scanner_bias_enabled": bool(cached_scanner_enabled),
        "current_scanner_bias_enabled": bool(current_scanner_enabled),
        "cached_monitor_bias_enabled": bool(cached_monitor_enabled),
        "current_monitor_bias_enabled": bool(current_monitor_enabled),
    }


def _cache_age_context(state: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any], int, int, int]:
    cache_payload = strategist_cache_payload(state)
    output = cache_payload.get("output") if isinstance(cache_payload.get("output"), dict) else {}
    now_epoch = runtime_now_epoch(state)
    generated_epoch = max(0, coerce_int(cache_payload.get("generated_epoch"), 0))
    reuse_sec = max(0, coerce_int(os.getenv("COMMANDER_STRATEGIST_CACHE_REUSE_SEC", "600"), 600))
    age_sec = max(0, now_epoch - generated_epoch) if generated_epoch > 0 else 10**9
    return cache_payload, output, generated_epoch, reuse_sec, age_sec


def assess_cached_strategist_reuse_preference(state: Dict[str, Any]) -> Dict[str, Any]:
    enabled, policy_source = resolve_commander_route_toggle(
        state,
        nested_path=("commander", "route", "cached_strategist_when_flat"),
        state_key="enable_cached_strategist_when_flat",
        default=False,
    )
    open_position_count = portfolio_open_position_count(state)
    cache_payload, cached_output, generated_epoch, reuse_sec, age_sec = _cache_age_context(state)
    payload = {
        "preferred": False,
        "enabled": bool(enabled),
        "policy_source": str(policy_source),
        "open_position_count": int(open_position_count),
        "reuse_sec": int(reuse_sec),
        "cache_age_sec": int(age_sec) if age_sec < 10**9 else None,
        "cache_source": str(cache_payload.get("source") or ""),
        "cached_output_present": bool(cached_output),
        "reason": "",
    }
    if not enabled:
        payload["reason"] = "disabled"
        return payload
    if open_position_count > 0:
        payload["reason"] = "open_positions_present"
        return payload
    if is_trueish(state.get("force_refresh_strategist")):
        payload["reason"] = "force_refresh_requested"
        return payload
    if not cached_output:
        payload["reason"] = "no_cached_strategist_output"
        return payload
    if generated_epoch <= 0:
        payload["reason"] = "cache_timestamp_missing"
        return payload
    if age_sec > reuse_sec:
        payload["reason"] = "cache_stale"
        return payload
    memory_context = assess_cached_strategist_memory_context(state, cached_output)
    payload.update({k: v for k, v in memory_context.items() if k != "mismatch"})
    if bool(memory_context.get("mismatch")):
        payload["reason"] = "cached_memory_context_mismatch"
        return payload
    payload["preferred"] = True
    payload["reason"] = "commander_preferred_cached_strategist"
    return payload


def should_use_cached_strategist_when_flat(state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    enabled, policy_source = resolve_commander_route_toggle(
        state,
        nested_path=("commander", "route", "cached_strategist_when_flat"),
        state_key="enable_cached_strategist_when_flat",
        default=False,
    )
    open_position_count = portfolio_open_position_count(state)
    _, output, generated_epoch, reuse_sec, age_sec = _cache_age_context(state)
    payload = {
        "enabled": bool(enabled),
        "policy_source": str(policy_source),
        "open_position_count": int(open_position_count),
        "reuse_sec": int(reuse_sec),
        "cache_age_sec": int(age_sec) if age_sec < 10**9 else None,
        "reason": "",
    }
    commander_decision = state.get("commander_decision") if isinstance(state.get("commander_decision"), dict) else {}
    strategist_refresh_requested = bool(commander_decision.get("strategist_refresh_requested"))
    strategist_refresh_context = (
        dict(commander_decision.get("strategist_refresh_context") or {})
        if isinstance(commander_decision.get("strategist_refresh_context"), dict)
        else {}
    )
    if not enabled:
        payload["reason"] = "disabled"
        return False, payload
    if open_position_count > 0:
        payload["reason"] = "open_positions_present"
        return False, payload
    if strategist_refresh_requested:
        payload.update({k: v for k, v in strategist_refresh_context.items() if k != "reason"})
        payload["source"] = "commander_decision"
        payload["refresh_signal"] = str(
            commander_decision.get("strategist_refresh_reason")
            or strategist_refresh_context.get("refresh_signal")
            or ""
        )
        payload["reason"] = "commander_requested_refresh"
        return False, payload
    if is_trueish(state.get("force_refresh_strategist")):
        payload["reason"] = "force_refresh_requested"
        return False, payload
    if not output:
        payload["reason"] = "no_cached_strategist_output"
        return False, payload
    if generated_epoch <= 0:
        payload["reason"] = "cache_timestamp_missing"
        return False, payload
    if age_sec > reuse_sec:
        payload["reason"] = "cache_stale"
        return False, payload
    memory_context = assess_cached_strategist_memory_context(state, output)
    payload.update({k: v for k, v in memory_context.items() if k != "mismatch"})
    if bool(memory_context.get("mismatch")):
        payload["reason"] = "cached_memory_context_mismatch"
        return False, payload
    payload["reason"] = "flat_position_cached_strategist"
    return True, payload


def should_use_cached_strategist_from_commander_skip(state: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    commander_decision = state.get("commander_decision") if isinstance(state.get("commander_decision"), dict) else {}
    strategist_invocation = str(commander_decision.get("strategist_invocation") or "").strip().upper()
    llm_policy = str(commander_decision.get("llm_policy") or "").strip().upper()
    open_position_count = portfolio_open_position_count(state)
    _, output, generated_epoch, reuse_sec, age_sec = _cache_age_context(state)
    payload = {
        "enabled": True,
        "source": "commander_decision",
        "strategist_invocation": strategist_invocation,
        "llm_policy": llm_policy,
        "open_position_count": int(open_position_count),
        "reuse_sec": int(reuse_sec),
        "cache_age_sec": int(age_sec) if age_sec < 10**9 else None,
        "reason": "",
    }
    strategist_refresh_requested = bool(commander_decision.get("strategist_refresh_requested"))
    strategist_refresh_context = (
        dict(commander_decision.get("strategist_refresh_context") or {})
        if isinstance(commander_decision.get("strategist_refresh_context"), dict)
        else {}
    )
    if open_position_count > 0:
        payload["reason"] = "open_positions_present"
        return False, payload
    if strategist_refresh_requested:
        payload.update({k: v for k, v in strategist_refresh_context.items() if k != "reason"})
        payload["refresh_signal"] = str(
            commander_decision.get("strategist_refresh_reason")
            or strategist_refresh_context.get("refresh_signal")
            or ""
        )
        payload["reason"] = "commander_requested_refresh"
        return False, payload
    if strategist_invocation != "SKIP":
        payload["reason"] = "commander_hint_not_skip"
        return False, payload
    if is_trueish(state.get("force_refresh_strategist")):
        payload["reason"] = "force_refresh_requested"
        return False, payload
    if not output:
        payload["reason"] = "no_cached_strategist_output"
        return False, payload
    if generated_epoch <= 0:
        payload["reason"] = "cache_timestamp_missing"
        return False, payload
    if age_sec > reuse_sec:
        payload["reason"] = "cache_stale"
        return False, payload
    memory_context = assess_cached_strategist_memory_context(state, output)
    payload.update({k: v for k, v in memory_context.items() if k != "mismatch"})
    if bool(memory_context.get("mismatch")):
        payload["reason"] = "cached_memory_context_mismatch"
        return False, payload
    payload["reason"] = "commander_skip_cached_strategist"
    return True, payload
