from __future__ import annotations

from typing import Any, Dict


def _to_int(v: Any) -> int:
    try:
        return int(float(v))
    except Exception:
        return 0


def evaluate_entry_guard(
    *,
    entry_info: Dict[str, Any],
    entry_quality_gate: Dict[str, Any],
    entry_cost_filter: Dict[str, Any],
    selected_already_held: bool,
    selected_pending_buy: bool,
    max_positions_reached: bool,
    closeout_window_active: bool,
    buy_blocked_post_exit_cooldown: bool,
    entry_intent_cooldown_sec: int,
    cooldown_until: int,
    now_epoch: int,
    forced_entry_block_reason: str = "",
) -> Dict[str, Any]:
    out_entry = dict(entry_info or {})
    guard_blocked = False
    guard_reason = ""
    buy_blocked_open_position = False
    buy_blocked_closeout_window = False
    buy_blocked_same_symbol = False
    buy_blocked_pending_buy = False

    forced_reason = str(forced_entry_block_reason or "").strip()
    if forced_reason:
        guard_blocked = True
        guard_reason = forced_reason
        if forced_reason == "same_symbol_loss_reentry_blocked":
            buy_blocked_same_symbol = True
        else:
            buy_blocked_open_position = True
    elif selected_already_held:
        guard_blocked = True
        guard_reason = "same_symbol_position_open"
        buy_blocked_open_position = True
        buy_blocked_same_symbol = True
    elif selected_pending_buy:
        guard_blocked = True
        guard_reason = "same_symbol_pending_buy"
        buy_blocked_pending_buy = True
    elif max_positions_reached:
        guard_blocked = True
        guard_reason = "max_positions_reached"
        buy_blocked_open_position = True
    elif closeout_window_active:
        guard_blocked = True
        guard_reason = "buy_blocked_closeout_window"
        buy_blocked_closeout_window = True
    elif buy_blocked_post_exit_cooldown:
        guard_blocked = True
        guard_reason = "post_exit_cooldown"
    elif entry_intent_cooldown_sec > 0 and cooldown_until > now_epoch:
        guard_blocked = True
        guard_reason = f"entry_guard_cooldown:{max(0, cooldown_until - now_epoch)}s_remaining"
    elif bool(entry_quality_gate.get("blocked")):
        guard_blocked = True
        guard_reason = str(entry_quality_gate.get("reason") or "entry_quality_gate_blocked")
        failed_checks = list(out_entry.get("failed_checks") or [])
        if "entry_quality_gate" not in failed_checks:
            failed_checks.append("entry_quality_gate")
        for reason_item in list(entry_quality_gate.get("reasons") or []):
            if reason_item not in failed_checks:
                failed_checks.append(str(reason_item))
        out_entry["failed_checks"] = failed_checks
        out_entry["primary_failure_axis"] = "entry_quality_gate"
    elif bool(out_entry.get("triggered")) and not bool(entry_cost_filter.get("passed")):
        guard_blocked = True
        guard_reason = "cost_adjusted_edge_not_ready"
        failed_checks = list(out_entry.get("failed_checks") or [])
        if "cost_adjusted_edge_ok" not in failed_checks:
            failed_checks.append("cost_adjusted_edge_ok")
        out_entry["failed_checks"] = failed_checks
        out_entry["primary_failure_axis"] = "cost_adjusted_edge"

    out_entry["guard_blocked"] = bool(guard_blocked)
    out_entry["guard_reason"] = str(guard_reason)
    out_entry["buy_blocked_same_symbol"] = bool(buy_blocked_same_symbol)
    out_entry["buy_blocked_pending_buy"] = bool(buy_blocked_pending_buy)
    out_entry["max_positions_reached"] = bool(max_positions_reached)

    return {
        "entry_info": out_entry,
        "entry_guard_blocked": bool(guard_blocked),
        "entry_guard_reason": str(guard_reason),
        "buy_blocked_open_position": bool(buy_blocked_open_position),
        "buy_blocked_closeout_window": bool(buy_blocked_closeout_window),
        "buy_blocked_same_symbol": bool(buy_blocked_same_symbol),
        "buy_blocked_pending_buy": bool(buy_blocked_pending_buy),
        "max_positions_reached": bool(max_positions_reached),
        "entry_intent_cooldown_remaining_sec": max(0, _to_int(cooldown_until) - _to_int(now_epoch)),
    }
