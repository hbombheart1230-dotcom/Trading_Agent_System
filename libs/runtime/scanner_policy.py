from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def _is_trueish(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _read_nested(root: Dict[str, Any], *path: str) -> Any:
    cursor: Any = root
    for key in path:
        if not isinstance(cursor, dict):
            return None
        cursor = cursor.get(key)
    return cursor


def _pick_value(*pairs: Tuple[str, Any]) -> Tuple[Any, str]:
    for source, value in pairs:
        if value not in (None, ""):
            return value, source
    return None, "default"


def normalize_scanner_source_type(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw in ("static", "strategist", "strategist_candidates", "provided"):
        return "static"
    if raw in ("hybrid", "auto"):
        return "hybrid"
    return "kiwoom"


def resolve_scanner_runtime_policy(
    state: Dict[str, Any],
    policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    policy = policy if isinstance(policy, dict) else {}
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    applied_scanner = applied_policy.get("scanner") if isinstance(applied_policy.get("scanner"), dict) else {}
    scanner_policy = policy.get("scanner") if isinstance(policy.get("scanner"), dict) else {}

    source_raw, source_source = _pick_value(
        ("commander_applied_policy", _read_nested(applied_scanner, "source", "type")),
        ("state_fallback", state.get("candidate_source")),
        ("policy_scanner", _read_nested(scanner_policy, "source", "type")),
        ("policy_flat_fallback", policy.get("candidate_source")),
    )
    strict_raw, strict_source = _pick_value(
        ("commander_applied_policy", _read_nested(applied_scanner, "kiwoom", "strict_only")),
        ("state_fallback", state.get("strict_kiwoom_candidates_only")),
        ("policy_scanner", _read_nested(scanner_policy, "kiwoom", "strict_only")),
        ("policy_flat_fallback", policy.get("strict_kiwoom_candidates_only")),
    )
    block_raw, block_source = _pick_value(
        ("commander_applied_policy", _read_nested(applied_scanner, "fallback", "block_static_when_empty")),
        ("state_fallback", state.get("block_static_fallback_when_kiwoom_empty")),
        ("policy_scanner", _read_nested(scanner_policy, "fallback", "block_static_when_empty")),
        ("policy_flat_fallback", policy.get("block_static_fallback_when_kiwoom_empty")),
    )
    live_fetch_raw, live_fetch_source = _pick_value(
        ("commander_applied_policy", _read_nested(applied_scanner, "kiwoom", "live_fetch")),
        ("state_fallback", state.get("kiwoom_candidate_live_fetch")),
        ("policy_scanner", _read_nested(scanner_policy, "kiwoom", "live_fetch")),
        ("policy_flat_fallback", policy.get("kiwoom_candidate_live_fetch")),
        ("policy_flat_fallback", policy.get("kiwoom_live_fetch")),
    )
    include_change_raw, include_change_source = _pick_value(
        ("commander_applied_policy", _read_nested(applied_scanner, "kiwoom", "include_change_rate")),
        ("state_fallback", state.get("kiwoom_candidate_include_change_rate")),
        ("state_fallback", state.get("kiwoom_include_change_rate")),
        ("policy_scanner", _read_nested(scanner_policy, "kiwoom", "include_change_rate")),
        ("policy_flat_fallback", policy.get("kiwoom_include_change_rate")),
    )

    source_type = normalize_scanner_source_type(source_raw)
    strict_only = _is_trueish(strict_raw) if strict_raw not in (None, "") else False
    block_static_when_empty = _is_trueish(block_raw) if block_raw not in (None, "") else True
    live_fetch = _is_trueish(live_fetch_raw) if live_fetch_raw not in (None, "") else False
    include_change_rate = _is_trueish(include_change_raw) if include_change_raw not in (None, "") else True

    if strict_only:
        fallback_mode = "strict_kiwoom_only"
    elif block_static_when_empty:
        fallback_mode = "block_static_when_empty"
    else:
        fallback_mode = "allow_static_fallback"

    sources = {
        "source_type": source_source,
        "strict_only": strict_source,
        "block_static_when_empty": block_source,
        "live_fetch": live_fetch_source,
        "include_change_rate": include_change_source,
    }
    overall_source = "default"
    for source_name in sources.values():
        if source_name != "default":
            overall_source = source_name
            break

    return {
        "source_type": source_type,
        "strict_only": bool(strict_only),
        "block_static_when_empty": bool(block_static_when_empty),
        "live_fetch": bool(live_fetch),
        "include_change_rate": bool(include_change_rate),
        "fallback_mode": str(fallback_mode),
        "policy_source": str(overall_source),
        "field_sources": sources,
    }
