from __future__ import annotations

from collections.abc import Callable
from typing import Any, Dict

from libs.core.symbols import normalize_symbol
from libs.runtime.monitor_exit.preview import preview_exit_decision_for_symbol
from libs.runtime.monitor_exit.reasons import exit_reason_priority


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


def select_exit_symbol(
    selected_symbol: str,
    pos_map: Dict[str, Dict[str, Any]],
    *,
    state: Dict[str, Any] | None = None,
    selected: Dict[str, Any] | None = None,
    policy: Dict[str, Any] | None = None,
    exit_policy_base: Dict[str, Any] | None = None,
    preview_resolver: Callable[..., Dict[str, Any]] | None = None,
) -> str:
    sel = normalize_symbol(selected_symbol)
    if state is None and sel and max(0, _to_int((pos_map.get(sel) or {}).get("qty"))) > 0:
        return sel

    held_symbols = [
        normalize_symbol(sym)
        for sym, row in pos_map.items()
        if max(0, _to_int((row or {}).get("qty"))) > 0
    ]
    held_symbols = [symbol for symbol in held_symbols if symbol]
    if not held_symbols:
        return sel

    if state is None:
        best_symbol = ""
        best_qty = 0
        for sym, row in pos_map.items():
            qty = max(0, _to_int((row or {}).get("qty")))
            if qty > best_qty:
                best_qty = qty
                best_symbol = normalize_symbol(sym)
        return best_symbol or sel

    base = exit_policy_base if isinstance(exit_policy_base, dict) else {}
    selected_raw = selected if isinstance(selected, dict) else {}
    selected_raw_symbol = normalize_symbol(selected_raw.get("symbol"))
    best_symbol = held_symbols[0]
    best_rank = (-1, -1, -1.0, -1, -1)
    resolver = preview_resolver or preview_exit_decision_for_symbol
    for sym in held_symbols:
        pos = dict(pos_map.get(sym) or {})
        selected_for_exit = selected_raw if selected_raw_symbol == sym else {"symbol": sym}
        decision = resolver(
            state=state,
            symbol=sym,
            position=pos,
            selected=selected_for_exit,
            exit_policy_base=base,
        )
        triggered = 1 if bool(decision.get("triggered")) else 0
        reason_priority = exit_reason_priority(str(decision.get("reason") or ""))
        pnl_mag = abs(_to_float(decision.get("_pnl_ratio")))
        selected_bonus = 1 if sym == sel else 0
        qty = max(0, _to_int(decision.get("_qty")))
        rank = (triggered, reason_priority, pnl_mag, selected_bonus, qty)
        if rank > best_rank:
            best_rank = rank
            best_symbol = sym
    if best_symbol:
        return best_symbol
    return sel
