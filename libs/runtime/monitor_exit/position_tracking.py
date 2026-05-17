from __future__ import annotations

import time
from typing import Any, Dict

from libs.core.symbols import normalize_symbol
from libs.runtime.monitor_exit.numeric import to_float


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def _resolve_now_epoch(state: Dict[str, Any]) -> int:
    for key in ("tick_ts", "now_epoch", "timestamp"):
        value = _to_int(state.get(key))
        if value > 0:
            return int(value)
    try:
        return int(time.time())
    except Exception:
        return 0


def position_hold_seconds(state: Dict[str, Any], symbol: str, position: Dict[str, Any]) -> int:
    for key in ("hold_sec", "position_age_seconds"):
        hold_sec = _to_int(position.get(key))
        if hold_sec > 0:
            return int(hold_sec)

    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    now_epoch = _resolve_now_epoch(state)
    entry_epoch = _to_int(
        position.get("position_entry_epoch")
        if position.get("position_entry_epoch") not in (None, "")
        else position.get("entry_epoch")
    )
    entry_map = (
        persisted.get("position_entry_epoch_by_symbol")
        if isinstance(persisted.get("position_entry_epoch_by_symbol"), dict)
        else {}
    )
    normalized_symbol = normalize_symbol(symbol)
    if entry_epoch <= 0:
        entry_epoch = _to_int(entry_map.get(normalized_symbol))
    if entry_epoch > 0 and now_epoch > 0:
        return max(0, int(now_epoch - entry_epoch))

    last_trade_side = str(persisted.get("last_trade_side") or "").strip().upper()
    last_trade_epoch = _to_int(persisted.get("last_trade_epoch"))
    last_trade_symbol = normalize_symbol(persisted.get("last_trade_symbol"))
    if last_trade_side == "BUY" and last_trade_epoch > 0 and (not last_trade_symbol or last_trade_symbol == normalized_symbol):
        return max(0, int(now_epoch - last_trade_epoch))
    if last_trade_side == "BUY" and last_trade_epoch > 0:
        legacy_age = max(0, int(now_epoch - last_trade_epoch))
        if legacy_age >= 12 * 3600:
            return int(legacy_age)
    return 0


def update_position_peak_price(
    state: Dict[str, Any],
    symbol: str,
    *,
    avg_price: float,
    observed_price: float,
) -> float:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    peak_map = persisted.get("position_peak_price") if isinstance(persisted.get("position_peak_price"), dict) else {}
    normalized_symbol = normalize_symbol(symbol)
    cur_peak = to_float(peak_map.get(normalized_symbol))
    next_peak = max(cur_peak, to_float(avg_price), to_float(observed_price))
    if normalized_symbol and next_peak > 0.0:
        peak_map[normalized_symbol] = float(next_peak)
        persisted["position_peak_price"] = peak_map
        state["persisted_state"] = persisted
    return float(next_peak)


def ensure_position_peak_price_map(
    state: Dict[str, Any],
    pos_map: Dict[str, Dict[str, Any]],
) -> Dict[str, float]:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    raw_peak_map = persisted.get("position_peak_price") if isinstance(persisted.get("position_peak_price"), dict) else {}
    next_peak_map: Dict[str, float] = {}
    for sym, row in pos_map.items():
        if max(0, _to_int((row or {}).get("qty"))) <= 0:
            continue
        key = normalize_symbol(sym)
        if not key:
            continue
        peak = to_float(raw_peak_map.get(key))
        avg_price = to_float((row or {}).get("avg_price"))
        position_peak = to_float((row or {}).get("peak_price"))
        high_water_mark = to_float((row or {}).get("high_water_mark"))
        next_peak = max(peak, avg_price, position_peak, high_water_mark)
        if next_peak > 0.0:
            next_peak_map[key] = float(next_peak)
    if next_peak_map:
        persisted["position_peak_price"] = next_peak_map
    else:
        persisted.pop("position_peak_price", None)
    state["persisted_state"] = persisted
    return next_peak_map
