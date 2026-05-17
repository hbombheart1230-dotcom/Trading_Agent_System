from __future__ import annotations

from typing import Any, Dict, List

from libs.runtime.monitor_exit.numeric import to_float


def empty_vwap_breakdown_confirmation(source: str = "") -> Dict[str, Any]:
    return {
        "vwap_breakdown_confirmation_available": False,
        "vwap_breakdown_consecutive_bars": 0,
        "vwap_breakdown_low_break_confirmed": False,
        "vwap_breakdown_volume_confirmed": False,
        "vwap_breakdown_confirmation_source": str(source or ""),
    }


def calculate_vwap_breakdown_confirmation(
    rows: List[Dict[str, Any]],
    *,
    source: str,
    threshold: float,
    volume_ratio: Any = None,
    volume_ratio_min: Any = None,
    low_break_pct: Any = None,
) -> Dict[str, Any]:
    normalized_rows = [row for row in rows if isinstance(row, dict)]
    if not normalized_rows:
        return empty_vwap_breakdown_confirmation("minute_rows_empty")

    latest = normalized_rows[-1]
    prior = normalized_rows[-2] if len(normalized_rows) >= 2 and isinstance(normalized_rows[-2], dict) else {}
    out = empty_vwap_breakdown_confirmation(source)
    out["vwap_breakdown_confirmation_available"] = True

    threshold_value = max(0.0, float(threshold or 0.0))
    consecutive = 0
    for row in reversed(normalized_rows):
        close = to_float(row.get("close"))
        vwap = to_float(row.get("vwap"))
        if close <= 0.0 or vwap <= 0.0:
            break
        if ((close - vwap) / vwap) <= -threshold_value:
            consecutive += 1
            continue
        break
    out["vwap_breakdown_consecutive_bars"] = int(consecutive)

    latest_low = to_float(latest.get("low"))
    prior_low = to_float(prior.get("low"))
    low_break_threshold = max(0.0, to_float(low_break_pct, 0.0))
    if latest_low > 0.0 and prior_low > 0.0 and latest_low <= float(prior_low * (1.0 - low_break_threshold)):
        out["vwap_breakdown_low_break_confirmed"] = True

    latest_volume = to_float(latest.get("volume"))
    prior_volume = to_float(prior.get("volume"))
    volume_ratio_threshold = max(1.0, to_float(volume_ratio_min, 1.2))
    direct_volume_ratio = to_float(volume_ratio)
    if direct_volume_ratio >= volume_ratio_threshold:
        out["vwap_breakdown_volume_confirmed"] = True
    elif latest_volume > 0.0 and prior_volume > 0.0 and latest_volume >= float(prior_volume * volume_ratio_threshold):
        out["vwap_breakdown_volume_confirmed"] = True
    return out

