from __future__ import annotations

import os
from typing import Any, Dict

from graphs.nodes.skill_contracts import account_order_is_pending, account_order_side, extract_account_orders_rows
from libs.core.symbols import normalize_symbol
from libs.runtime.monitor_exit.policy_config import resolve_exit_policy_config
from libs.runtime.monitor_exit.runtime_clock import ensure_entry_market_context_clock_fields


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _is_trueish(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def resolve_max_positions(state: Dict[str, Any], policy: Dict[str, Any] | None = None) -> int:
    for value in (
        ((state.get("risk_context") or {}).get("max_positions") if isinstance(state.get("risk_context"), dict) else None),
        ((state.get("risk") or {}).get("max_positions") if isinstance(state.get("risk"), dict) else None),
        ((policy or {}).get("risk_max_positions") if isinstance(policy, dict) else None),
        os.getenv("RISK_MAX_POSITIONS"),
    ):
        try:
            if value not in (None, ""):
                return max(1, int(float(value)))
        except Exception:
            continue
    return 1


def pending_order_symbols_from_account_orders(state: Dict[str, Any], *, side: str = "") -> set[str]:
    try:
        rows, _meta = extract_account_orders_rows(state)
    except Exception:
        return set()
    side_filter = str(side or "").strip().upper()
    out: set[str] = set()
    for row in rows:
        if not isinstance(row, dict) or not account_order_is_pending(row):
            continue
        if side_filter and account_order_side(row) != side_filter:
            continue
        symbol = normalize_symbol(row.get("symbol") or row.get("stk_cd") or row.get("pdno") or row.get("code"))
        if not symbol:
            continue
        out.add(symbol)
    return out


def pending_buy_symbols_from_account_orders(state: Dict[str, Any]) -> set[str]:
    return pending_order_symbols_from_account_orders(state, side="BUY")


def features_pending_order_count(features: Dict[str, Any]) -> int:
    if not isinstance(features, dict):
        return 0
    if not bool(features.get("skill_open_orders_pending_only")):
        return 0
    return max(0, _to_int(features.get("skill_open_orders")))


def resolve_block_buy_when_open_position(
    state: Dict[str, Any],
    policy: Dict[str, Any],
    monitor_policy: Dict[str, Any],
) -> bool:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    applied_entry = (applied_policy.get("monitor") or {}).get("entry") if isinstance((applied_policy.get("monitor") or {}), dict) else {}
    if isinstance(applied_entry, dict) and applied_entry.get("block_buy_when_open_position") is not None:
        return _is_trueish(applied_entry.get("block_buy_when_open_position"))
    if state.get("monitor_block_buy_when_open_position") is not None:
        return _is_trueish(state.get("monitor_block_buy_when_open_position"))
    if isinstance(monitor_policy, dict) and monitor_policy.get("block_buy_when_open_position") is not None:
        return _is_trueish(monitor_policy.get("block_buy_when_open_position"))
    if isinstance(policy, dict) and policy.get("block_buy_when_open_position") is not None:
        return _is_trueish(policy.get("block_buy_when_open_position"))
    raw_env = str(os.getenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "") or "").strip()
    if raw_env:
        return _is_trueish(raw_env)
    return True


def resolve_entry_closeout_window_guard(
    state: Dict[str, Any],
    policy: Dict[str, Any],
) -> Dict[str, Any]:
    exit_policy = resolve_exit_policy_config(state, policy)
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    applied_entry = (
        ((applied_policy.get("monitor") or {}).get("entry") or {})
        if isinstance((applied_policy.get("monitor") or {}).get("entry"), dict)
        else {}
    )
    policy_entry = (
        ((policy.get("monitor") or {}).get("entry") or {})
        if isinstance((policy.get("monitor") or {}).get("entry"), dict)
        else {}
    )
    market_ctx = ensure_entry_market_context_clock_fields(state)
    minutes_to_close = _optional_float(market_ctx.get("minutes_to_close"))
    use_eod_flat = bool(exit_policy.get("use_eod_flat"))
    cutoff_min = int(_to_float(exit_policy.get("eod_flat_cutoff_min") or 10))
    buy_cutoff_raw = (
        applied_entry.get("buy_closeout_cutoff_min")
        if applied_entry.get("buy_closeout_cutoff_min") not in (None, "")
        else policy_entry.get("buy_closeout_cutoff_min")
    )
    buy_cutoff_min = int(_optional_float(buy_cutoff_raw) or max(15.0, float(cutoff_min)))
    if buy_cutoff_min <= 0:
        buy_cutoff_min = max(15, int(cutoff_min))
    buy_cutoff_min = max(int(cutoff_min), int(buy_cutoff_min))
    active = bool(
        use_eod_flat
        and minutes_to_close is not None
        and minutes_to_close >= 0.0
        and minutes_to_close <= float(buy_cutoff_min)
    )
    return {
        "active": active,
        "minutes_to_close": minutes_to_close,
        "cutoff_min": int(cutoff_min),
        "buy_cutoff_min": int(buy_cutoff_min),
        "use_eod_flat": bool(use_eod_flat),
        "reason": "buy_blocked_closeout_window" if active else "",
    }
