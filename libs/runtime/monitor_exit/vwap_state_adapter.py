from __future__ import annotations

from typing import Any, Dict

from libs.core.symbols import normalize_symbol
from libs.runtime.monitor_exit.adapters.state_data import (
    fresh_minute_vwap_distance_for_symbol,
    minute_rows_for_symbol,
)
from libs.runtime.monitor_exit.vwap_confirmation import (
    calculate_vwap_breakdown_confirmation,
    empty_vwap_breakdown_confirmation,
)


def vwap_breakdown_confirmation_for_symbol(
    state: Dict[str, Any],
    symbol: str,
    *,
    threshold: float,
    volume_ratio: Any = None,
    volume_ratio_min: Any = None,
    low_break_pct: Any = None,
) -> Dict[str, Any]:
    sym = normalize_symbol(symbol)
    if not sym:
        return empty_vwap_breakdown_confirmation()
    rows, source = minute_rows_for_symbol(state, sym)
    if not rows:
        return empty_vwap_breakdown_confirmation("minute_rows_unavailable")
    return calculate_vwap_breakdown_confirmation(
        rows,
        source=source,
        threshold=threshold,
        volume_ratio=volume_ratio,
        volume_ratio_min=volume_ratio_min,
        low_break_pct=low_break_pct,
    )
