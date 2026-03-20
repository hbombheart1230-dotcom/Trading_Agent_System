from __future__ import annotations

import os
from typing import Any, Dict, List, Mapping, Sequence


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _env_float(name: str, default: float) -> float:
    raw = str(os.getenv(name, "") or "").strip()
    return _to_float(raw, default) if raw else float(default)


def _env_int(name: str, default: int) -> int:
    raw = str(os.getenv(name, "") or "").strip()
    return _to_int(raw, default) if raw else int(default)


def _candles_from_rows(rows: Sequence[Mapping[str, Any]] | None) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw in list(rows or []):
        if not isinstance(raw, Mapping):
            continue
        open_px = _to_float(raw.get("open"))
        high_px = _to_float(raw.get("high"))
        low_px = _to_float(raw.get("low"))
        close_px = _to_float(raw.get("close"))
        volume = _to_float(raw.get("volume"))
        if high_px <= 0.0 and low_px <= 0.0 and close_px <= 0.0:
            continue
        out.append(
            {
                "ts": raw.get("ts"),
                "open": open_px or close_px,
                "high": max(high_px, open_px, close_px),
                "low": min(low_px if low_px > 0.0 else close_px or open_px, open_px or close_px, close_px or open_px),
                "close": close_px or open_px,
                "volume": max(0.0, volume),
                "vwap": raw.get("vwap"),
            }
        )
    return out


def _merge_candle_group(group: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    rows = [row for row in group if isinstance(row, Mapping)]
    if not rows:
        return {}
    open_px = _to_float(rows[0].get("open"))
    close_px = _to_float(rows[-1].get("close"))
    high_px = max(_to_float(row.get("high"), close_px) for row in rows)
    low_px = min(_to_float(row.get("low"), open_px if open_px > 0.0 else close_px) for row in rows)
    volume = sum(max(0.0, _to_float(row.get("volume"))) for row in rows)
    weighted_vwap_num = 0.0
    weighted_vwap_den = 0.0
    for row in rows:
        row_volume = max(0.0, _to_float(row.get("volume")))
        row_vwap = _to_float(row.get("vwap"))
        if row_volume > 0.0 and row_vwap > 0.0:
            weighted_vwap_num += row_vwap * row_volume
            weighted_vwap_den += row_volume
    merged: Dict[str, Any] = {
        "ts": rows[-1].get("ts"),
        "open": open_px or close_px,
        "high": high_px,
        "low": low_px,
        "close": close_px or open_px,
        "volume": volume,
    }
    if weighted_vwap_den > 0.0:
        merged["vwap"] = weighted_vwap_num / weighted_vwap_den
    return merged


def _compress_candles(rows: Sequence[Mapping[str, Any]], timeframe_minutes: int) -> List[Dict[str, Any]]:
    candles = _candles_from_rows(rows)
    bucket = max(1, int(timeframe_minutes or 1))
    if bucket <= 1 or len(candles) <= 1:
        return candles
    out: List[Dict[str, Any]] = []
    chunk: List[Mapping[str, Any]] = []
    for row in candles:
        chunk.append(row)
        if len(chunk) >= bucket:
            merged = _merge_candle_group(chunk)
            if merged:
                out.append(merged)
            chunk = []
    if chunk:
        merged = _merge_candle_group(chunk)
        if merged:
            out.append(merged)
    return out


def _session_vwap(candles: Sequence[Mapping[str, Any]]) -> float | None:
    weighted_num = 0.0
    weighted_den = 0.0
    for row in candles:
        volume = max(0.0, _to_float(row.get("volume")))
        if volume <= 0.0:
            continue
        vwap = _to_float(row.get("vwap"))
        if vwap <= 0.0:
            high_px = _to_float(row.get("high"))
            low_px = _to_float(row.get("low"))
            close_px = _to_float(row.get("close"))
            vwap = (high_px + low_px + close_px) / 3.0
        if vwap <= 0.0:
            continue
        weighted_num += vwap * volume
        weighted_den += volume
    if weighted_den <= 0.0:
        return None
    return weighted_num / weighted_den


def resolve_intraday_entry_policy(
    policy: Mapping[str, Any] | None = None,
    *,
    frame: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    cfg = dict(policy or {})
    out = {
        "enabled": bool(cfg.get("intraday_entry_enabled", True)),
        "timeframe_minutes": max(1, _to_int(cfg.get("entry_timeframe_minutes"), _env_int("MONITOR_ENTRY_TIMEFRAME_MINUTES", 1))),
        "breakout_lookback": max(3, _to_int(cfg.get("entry_breakout_lookback"), _env_int("MONITOR_ENTRY_BREAKOUT_LOOKBACK", 5))),
        "volume_lookback": max(3, _to_int(cfg.get("entry_volume_lookback"), _env_int("MONITOR_ENTRY_VOLUME_LOOKBACK", 5))),
        "volume_ratio_min": max(0.1, _to_float(cfg.get("entry_volume_ratio_min"), _env_float("MONITOR_ENTRY_VOLUME_RATIO_MIN", 1.15))),
        "max_extended_from_vwap_pct": max(0.0, _to_float(cfg.get("entry_max_extended_from_vwap_pct"), _env_float("MONITOR_ENTRY_MAX_EXTENDED_FROM_VWAP_PCT", 0.006))),
        "pullback_max_pct": max(0.0, _to_float(cfg.get("entry_pullback_max_pct"), _env_float("MONITOR_ENTRY_PULLBACK_MAX_PCT", 0.008))),
        "reclaim_tolerance_pct": max(0.0, _to_float(cfg.get("entry_reclaim_tolerance_pct"), _env_float("MONITOR_ENTRY_RECLAIM_TOLERANCE_PCT", 0.0015))),
        "breakout_buffer_pct": max(0.0, _to_float(cfg.get("entry_breakout_buffer_pct"), _env_float("MONITOR_ENTRY_BREAKOUT_BUFFER_PCT", 0.0))),
        "intent_cooldown_sec": max(0, _to_int(cfg.get("entry_intent_cooldown_sec"), _env_int("MONITOR_ENTRY_INTENT_COOLDOWN_SEC", 60))),
    }
    adjustments: List[str] = []
    playbook = str((frame or {}).get("playbook") or "").strip().lower()
    guidance = str((frame or {}).get("monitor_guidance") or "").strip().lower()
    risk_tone = str((frame or {}).get("risk_tone") or "").strip().lower()
    aggressiveness = str((frame or {}).get("trade_aggressiveness") or "").strip().lower()

    if playbook == "breakout":
        out["volume_ratio_min"] = max(1.0, float(out["volume_ratio_min"]) - 0.05)
        out["max_extended_from_vwap_pct"] = min(0.015, float(out["max_extended_from_vwap_pct"]) + 0.001)
        adjustments.append("playbook:breakout")
    elif playbook in ("pullback", "reversal"):
        out["breakout_lookback"] = max(3, int(out["breakout_lookback"]) - 1)
        out["pullback_max_pct"] = min(0.02, float(out["pullback_max_pct"]) + 0.002)
        adjustments.append(f"playbook:{playbook}")
    elif playbook == "defensive":
        out["volume_ratio_min"] = min(2.0, float(out["volume_ratio_min"]) + 0.10)
        out["max_extended_from_vwap_pct"] = max(0.0025, float(out["max_extended_from_vwap_pct"]) - 0.001)
        adjustments.append("playbook:defensive")

    if guidance == "hold_through_noise":
        out["pullback_max_pct"] = min(0.02, float(out["pullback_max_pct"]) + 0.001)
        adjustments.append("guidance:hold_through_noise")
    elif guidance == "defensive_exit":
        out["volume_ratio_min"] = min(2.0, float(out["volume_ratio_min"]) + 0.05)
        adjustments.append("guidance:defensive_exit")

    if risk_tone == "conservative":
        out["volume_ratio_min"] = min(2.0, float(out["volume_ratio_min"]) + 0.05)
        out["max_extended_from_vwap_pct"] = max(0.0025, float(out["max_extended_from_vwap_pct"]) - 0.0005)
        adjustments.append("risk_tone:conservative")
    elif risk_tone == "aggressive":
        out["volume_ratio_min"] = max(0.9, float(out["volume_ratio_min"]) - 0.05)
        adjustments.append("risk_tone:aggressive")

    if aggressiveness == "low":
        out["volume_ratio_min"] = min(2.0, float(out["volume_ratio_min"]) + 0.05)
        adjustments.append("trade_aggressiveness:low")
    elif aggressiveness == "high":
        out["volume_ratio_min"] = max(0.9, float(out["volume_ratio_min"]) - 0.05)
        adjustments.append("trade_aggressiveness:high")

    out["adjustments"] = adjustments
    return out


def evaluate_intraday_entry_signal(
    rows: Sequence[Mapping[str, Any]] | None,
    *,
    current_price: Any = None,
    features: Mapping[str, Any] | None = None,
    policy: Mapping[str, Any] | None = None,
    frame: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    resolved_policy = resolve_intraday_entry_policy(policy, frame=frame)
    timeframe_minutes = int(resolved_policy.get("timeframe_minutes") or 1)
    candles = _compress_candles(rows or [], timeframe_minutes)
    out: Dict[str, Any] = {
        "enabled": bool(resolved_policy.get("enabled")),
        "evaluated": False,
        "triggered": False,
        "decision": "WAIT",
        "reason": "",
        "pattern": "",
        "signal_chain": [],
        "metrics": {},
        "thresholds": dict(resolved_policy),
    }
    if not out["enabled"]:
        out["reason"] = "intraday_entry_disabled"
        return out
    if not candles:
        out["reason"] = "minute_candle_missing"
        out["metrics"] = {
            "bar_count": 0,
            "min_required_bars": 0,
            "timeframe_minutes": timeframe_minutes,
            "price": _to_float(current_price) if _to_float(current_price) > 0.0 else None,
            "vwap": None,
            "vwap_distance": None,
            "volume_ratio": None,
            "recent_high": None,
            "pullback_pct": None,
        }
        return out
    min_required_bars = max(
        int(resolved_policy.get("breakout_lookback") or 5) + 1,
        int(resolved_policy.get("volume_lookback") or 5) + 1,
        4,
    )
    if len(candles) < min_required_bars:
        out["reason"] = "data_incomplete"
        out["metrics"] = {
            "bar_count": len(candles),
            "min_required_bars": min_required_bars,
            "timeframe_minutes": timeframe_minutes,
            "price": _to_float(current_price) if _to_float(current_price) > 0.0 else None,
            "vwap": _to_float(_session_vwap(candles), 0.0) or None,
            "vwap_distance": None,
            "volume_ratio": None,
            "recent_high": None,
            "pullback_pct": None,
        }
        return out

    out["evaluated"] = True
    last = candles[-1]
    prior = candles[-2]
    lookback = int(resolved_policy.get("breakout_lookback") or 5)
    volume_lookback = int(resolved_policy.get("volume_lookback") or 5)
    breakout_window = candles[-(lookback + 1):-1]
    volume_window = candles[-(volume_lookback + 1):-1]
    recent_high = max(_to_float(row.get("high")) for row in breakout_window)
    prior_bar_high = _to_float(prior.get("high"))
    prior_bar_low = _to_float(prior.get("low"))
    current_close = _to_float(current_price, _to_float(last.get("close")))
    current_high = _to_float(last.get("high"))
    current_low = _to_float(last.get("low"))
    current_volume = max(0.0, _to_float(last.get("volume")))
    average_volume = 0.0
    if volume_window:
        average_volume = sum(max(0.0, _to_float(row.get("volume"))) for row in volume_window) / float(len(volume_window))
    volume_ratio = (current_volume / average_volume) if average_volume > 0.0 else 0.0

    current_vwap = _to_float(last.get("vwap"))
    if current_vwap <= 0.0:
        current_vwap = _to_float(_session_vwap(candles), 0.0)
    previous_vwap = _to_float(prior.get("vwap"))
    if previous_vwap <= 0.0:
        previous_vwap = current_vwap

    extended_from_vwap_pct = 0.0
    if current_vwap > 0.0 and current_close > 0.0:
        extended_from_vwap_pct = (current_close / current_vwap) - 1.0

    prior_close = _to_float(prior.get("close"))
    reclaim_tolerance_pct = _to_float(resolved_policy.get("reclaim_tolerance_pct"))
    breakout_buffer_pct = _to_float(resolved_policy.get("breakout_buffer_pct"))
    breakout_level = recent_high * (1.0 + breakout_buffer_pct) if recent_high > 0.0 else 0.0
    breakout_ok = breakout_level > 0.0 and current_close >= breakout_level and current_high >= recent_high
    vwap_hold_ok = current_vwap > 0.0 and current_close >= current_vwap * (1.0 - reclaim_tolerance_pct)
    vwap_reclaim_ok = (
        current_vwap > 0.0
        and prior_close < previous_vwap * (1.0 - reclaim_tolerance_pct)
        and current_close >= current_vwap * (1.0 - reclaim_tolerance_pct)
    )
    pullback_lows = [max(0.0, _to_float(row.get("low"))) for row in candles[-4:-1]]
    pullback_floor = min([px for px in pullback_lows if px > 0.0], default=0.0)
    pullback_depth_pct = ((recent_high - pullback_floor) / recent_high) if recent_high > 0.0 and pullback_floor > 0.0 else 0.0
    rebound_ok = current_close > prior_bar_high and current_close >= prior_close
    volume_ok = volume_ratio >= _to_float(resolved_policy.get("volume_ratio_min"))
    extension_ok = extended_from_vwap_pct <= _to_float(resolved_policy.get("max_extended_from_vwap_pct"))
    pullback_ok = pullback_depth_pct <= _to_float(resolved_policy.get("pullback_max_pct"))

    if current_close <= 0.0 or recent_high <= 0.0 or current_vwap <= 0.0:
        out["reason"] = "data_incomplete"
        out["metrics"] = {
            "timeframe_minutes": timeframe_minutes,
            "bar_count": len(candles),
            "price": current_close if current_close > 0.0 else None,
            "vwap": current_vwap if current_vwap > 0.0 else None,
            "vwap_distance": extended_from_vwap_pct if current_vwap > 0.0 and current_close > 0.0 else None,
            "volume_ratio": volume_ratio if volume_ratio > 0.0 else None,
            "recent_high": recent_high if recent_high > 0.0 else None,
            "pullback_pct": pullback_depth_pct,
        }
        return out

    signal_chain: List[str] = []
    if breakout_ok:
        signal_chain.append("recent_high_breakout")
    if vwap_hold_ok:
        signal_chain.append("vwap_hold")
    if vwap_reclaim_ok:
        signal_chain.append("vwap_reclaim")
    if volume_ok:
        signal_chain.append("volume_confirmation")
    if rebound_ok:
        signal_chain.append("pullback_rebound")
    if extension_ok:
        signal_chain.append("not_extended")

    pattern = ""
    reason = ""
    triggered = False
    if breakout_ok and vwap_hold_ok and volume_ok and extension_ok:
        triggered = True
        pattern = "breakout_vwap_hold"
        reason = "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation"
    elif rebound_ok and vwap_hold_ok and volume_ok and pullback_ok and extension_ok:
        triggered = True
        pattern = "pullback_rebound"
        reason = "pullback_rebound_above_vwap_with_volume_confirmation"
    else:
        failed: List[str] = []
        if not extension_ok:
            failed.append("too_extended_from_vwap")
        if not volume_ok:
            failed.append("volume_insufficient")
        if not breakout_ok and not rebound_ok:
            failed.append("no_breakout_signal")
        if not vwap_hold_ok:
            failed.append("vwap_not_confirmed")
        if not pullback_ok:
            failed.append("pullback_too_deep")
        reason = failed[0] if failed else "entry_signal_not_confirmed"

    metrics = {
        "timeframe_minutes": timeframe_minutes,
        "bar_count": len(candles),
        "price": current_close if current_close > 0.0 else None,
        "current_price": current_close if current_close > 0.0 else None,
        "current_high": current_high if current_high > 0.0 else None,
        "current_low": current_low if current_low > 0.0 else None,
        "recent_high": recent_high if recent_high > 0.0 else None,
        "breakout_level": breakout_level if breakout_level > 0.0 else None,
        "prior_bar_high": prior_bar_high if prior_bar_high > 0.0 else None,
        "prior_bar_low": prior_bar_low if prior_bar_low > 0.0 else None,
        "vwap": current_vwap if current_vwap > 0.0 else None,
        "vwap_distance": extended_from_vwap_pct,
        "volume_ratio": volume_ratio if volume_ratio > 0.0 else None,
        "pullback_pct": pullback_depth_pct,
        "pullback_depth_pct": pullback_depth_pct,
        "extended_from_vwap_pct": extended_from_vwap_pct,
        "breakout_ok": bool(breakout_ok),
        "vwap_hold_ok": bool(vwap_hold_ok),
        "vwap_reclaim_ok": bool(vwap_reclaim_ok),
        "rebound_ok": bool(rebound_ok),
        "volume_ok": bool(volume_ok),
        "extension_ok": bool(extension_ok),
        "pullback_ok": bool(pullback_ok),
        "engine_vwap_distance": (features or {}).get("engine_vwap_distance"),
        "engine_volume_spike20": (features or {}).get("engine_volume_spike20"),
        "engine_trend_strength": (features or {}).get("engine_trend_strength"),
    }
    out.update(
        {
            "triggered": bool(triggered),
            "decision": "BUY" if triggered else "WAIT",
            "pattern": pattern,
            "reason": reason,
            "signal_chain": signal_chain,
            "metrics": metrics,
        }
    )
    return out
