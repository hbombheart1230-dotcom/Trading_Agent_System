from __future__ import annotations

import statistics
from dataclasses import replace
from typing import Any, Dict, List, Mapping, Sequence

from libs.runtime.monitor_policy import MonitorEntryPolicy


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


def _infer_spacing_seconds(candles: Sequence[Mapping[str, Any]]) -> float | None:
    ts_values: List[int] = []
    for row in candles:
        ts = _to_int(row.get("ts"), 0)
        if ts > 0:
            ts_values.append(ts)
    if len(ts_values) < 4:
        return None
    diffs: List[int] = []
    for prev_ts, cur_ts in zip(ts_values, ts_values[1:]):
        diff = int(cur_ts) - int(prev_ts)
        if diff > 0:
            diffs.append(diff)
    if len(diffs) < 3:
        return None
    try:
        return float(statistics.median(diffs))
    except Exception:
        return None


def _classify_series_quality(
    candles: Sequence[Mapping[str, Any]],
    *,
    timeframe_minutes: int,
) -> Dict[str, Any]:
    spacing_seconds = _infer_spacing_seconds(candles)
    if spacing_seconds is None:
        return {
            "intraday_compatible": True,
            "inferred_spacing_seconds": None,
            "inferred_spacing_minutes": None,
            "series_class": "unknown",
            "compatibility_reason": "timestamp_missing",
        }

    spacing_minutes = spacing_seconds / 60.0
    max_intraday_spacing_seconds = max(1800.0, float(max(1, timeframe_minutes)) * 60.0 * 6.0)
    intraday_compatible = spacing_seconds <= max_intraday_spacing_seconds
    if intraday_compatible:
        series_class = "intraday"
        compatibility_reason = "intraday_spacing_detected"
    elif spacing_seconds >= 12 * 3600:
        series_class = "daily_or_higher"
        compatibility_reason = "non_intraday_spacing_detected"
    else:
        series_class = "higher_timeframe"
        compatibility_reason = "non_intraday_spacing_detected"
    return {
        "intraday_compatible": intraday_compatible,
        "inferred_spacing_seconds": round(spacing_seconds, 3),
        "inferred_spacing_minutes": round(spacing_minutes, 3),
        "series_class": series_class,
        "compatibility_reason": compatibility_reason,
    }


def resolve_intraday_entry_policy(
    policy: Mapping[str, Any] | MonitorEntryPolicy | None = None,
    *,
    frame: Mapping[str, Any] | None = None,
) -> MonitorEntryPolicy:
    resolved = policy if isinstance(policy, MonitorEntryPolicy) else MonitorEntryPolicy.from_mapping(policy)
    adjustments: List[str] = []
    playbook = str((frame or {}).get("playbook") or "").strip().lower()
    guidance = str((frame or {}).get("monitor_guidance") or "").strip().lower()
    risk_tone = str((frame or {}).get("risk_tone") or "").strip().lower()
    aggressiveness = str((frame or {}).get("trade_aggressiveness") or "").strip().lower()

    if playbook == "breakout":
        resolved = replace(
            resolved,
            volume_ratio_min=max(1.0, float(resolved.volume_ratio_min)),
            max_extended_from_vwap_pct=min(0.03, max(float(resolved.max_extended_from_vwap_pct), 0.02)),
            pullback_max_pct=min(0.04, max(float(resolved.pullback_max_pct), 0.03)),
        )
        adjustments.append("playbook:breakout")
    elif playbook in ("pullback", "reversal"):
        resolved = replace(
            resolved,
            breakout_lookback=max(3, int(resolved.breakout_lookback) - 1),
            volume_ratio_min=max(0.68, min(float(resolved.volume_ratio_min), 0.9)),
            min_extended_from_vwap_pct=min(float(resolved.min_extended_from_vwap_pct), -0.005),
            max_extended_from_vwap_pct=max(float(resolved.max_extended_from_vwap_pct), 0.05),
            pullback_min_pct=max(0.008, float(resolved.pullback_min_pct) - 0.004),
            pullback_max_pct=max(float(resolved.pullback_max_pct), 0.06),
        )
        # Keep shallow pullback entries available during live pullback monitoring.
        adjustments.append(f"playbook:{playbook}")
    elif playbook == "defensive":
        resolved = replace(
            resolved,
            volume_ratio_min=min(1.1, float(resolved.volume_ratio_min) + 0.03),
            max_extended_from_vwap_pct=max(0.03, min(float(resolved.max_extended_from_vwap_pct), 0.05)),
            pullback_max_pct=min(float(resolved.pullback_max_pct), 0.05),
        )
        adjustments.append("playbook:defensive")

    if guidance == "hold_through_noise":
        resolved = replace(
            resolved,
            pullback_max_pct=min(0.07, float(resolved.pullback_max_pct) + 0.005),
        )
        adjustments.append("guidance:hold_through_noise")
    elif guidance == "defensive_exit":
        if playbook in ("pullback", "reversal"):
            resolved = replace(
                resolved,
                volume_ratio_min=max(0.68, min(1.0, float(resolved.volume_ratio_min) - 0.04)),
                max_extended_from_vwap_pct=max(0.05, float(resolved.max_extended_from_vwap_pct)),
            )
            adjustments.append("guidance:defensive_exit_pullback")
        else:
            next_max_extended = float(resolved.max_extended_from_vwap_pct)
            if playbook != "defensive":
                next_max_extended = max(0.03, float(resolved.max_extended_from_vwap_pct) - 0.0025)
            resolved = replace(
                resolved,
                volume_ratio_min=min(1.1, float(resolved.volume_ratio_min) + 0.01),
                max_extended_from_vwap_pct=next_max_extended,
            )
            adjustments.append("guidance:defensive_exit")

    if risk_tone == "conservative":
        if playbook in ("pullback", "reversal"):
            resolved = replace(
                resolved,
                volume_ratio_min=min(1.0, float(resolved.volume_ratio_min)),
                max_extended_from_vwap_pct=max(0.05, float(resolved.max_extended_from_vwap_pct)),
            )
            adjustments.append("risk_tone:conservative_pullback")
        else:
            next_max_extended = float(resolved.max_extended_from_vwap_pct)
            if playbook != "defensive":
                next_max_extended = max(0.03, float(resolved.max_extended_from_vwap_pct) - 0.0025)
            resolved = replace(
                resolved,
                volume_ratio_min=min(1.1, float(resolved.volume_ratio_min) + 0.01),
                max_extended_from_vwap_pct=next_max_extended,
            )
            adjustments.append("risk_tone:conservative")
    elif risk_tone == "aggressive":
        resolved = replace(
            resolved,
            volume_ratio_min=max(0.9, float(resolved.volume_ratio_min) - 0.05),
            max_extended_from_vwap_pct=min(0.08, float(resolved.max_extended_from_vwap_pct) + 0.01),
        )
        adjustments.append("risk_tone:aggressive")

    if aggressiveness == "low":
        if playbook in ("pullback", "reversal"):
            resolved = replace(
                resolved,
                volume_ratio_min=min(1.1, float(resolved.volume_ratio_min) + 0.02),
            )
            adjustments.append("trade_aggressiveness:low_pullback")
        else:
            resolved = replace(
                resolved,
                volume_ratio_min=min(1.2, float(resolved.volume_ratio_min) + 0.02),
            )
            adjustments.append("trade_aggressiveness:low")
    elif aggressiveness == "high":
        resolved = replace(
            resolved,
            volume_ratio_min=max(0.9, float(resolved.volume_ratio_min) - 0.05),
            max_extended_from_vwap_pct=min(0.08, float(resolved.max_extended_from_vwap_pct) + 0.005),
        )
        adjustments.append("trade_aggressiveness:high")

    return replace(resolved, adjustments=tuple(adjustments))


def evaluate_intraday_entry_signal(
    rows: Sequence[Mapping[str, Any]] | None,
    *,
    current_price: Any = None,
    features: Mapping[str, Any] | None = None,
    policy: Mapping[str, Any] | MonitorEntryPolicy | None = None,
    frame: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    resolved_policy = resolve_intraday_entry_policy(policy, frame=frame)
    applied_policy = resolved_policy.to_dict()
    timeframe_minutes = int(resolved_policy.timeframe_minutes or 1)
    candles = _compress_candles(rows or [], timeframe_minutes)
    out: Dict[str, Any] = {
        "enabled": bool(resolved_policy.enabled),
        "evaluated": False,
        "triggered": False,
        "decision": "WAIT",
        "reason": "",
        "pattern": "",
        "signal_chain": [],
        "metrics": {},
        "thresholds": dict(applied_policy),
        "applied_policy": dict(applied_policy),
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
        int(resolved_policy.breakout_lookback or 5) + 1,
        int(resolved_policy.volume_lookback or 5) + 1,
        4,
    )
    series_quality = _classify_series_quality(candles, timeframe_minutes=timeframe_minutes)
    out["series_quality"] = dict(series_quality)
    if not bool(series_quality.get("intraday_compatible")):
        out["reason"] = "minute_candle_missing"
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
            "inferred_spacing_minutes": series_quality.get("inferred_spacing_minutes"),
            "series_class": series_quality.get("series_class"),
            "compatibility_reason": series_quality.get("compatibility_reason"),
        }
        return out
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
            "inferred_spacing_minutes": series_quality.get("inferred_spacing_minutes"),
            "series_class": series_quality.get("series_class"),
        }
        return out

    out["evaluated"] = True
    last = candles[-1]
    prior = candles[-2]
    lookback = int(resolved_policy.breakout_lookback or 5)
    volume_lookback = int(resolved_policy.volume_lookback or 5)
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
    reclaim_tolerance_pct = _to_float(resolved_policy.reclaim_tolerance_pct)
    breakout_buffer_pct = _to_float(resolved_policy.breakout_buffer_pct)
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
    volume_ok = volume_ratio >= _to_float(resolved_policy.volume_ratio_min)
    min_extended_from_vwap_pct = _to_float(resolved_policy.min_extended_from_vwap_pct)
    max_extended_from_vwap_pct = _to_float(resolved_policy.max_extended_from_vwap_pct)
    extension_ok = min_extended_from_vwap_pct <= extended_from_vwap_pct <= max_extended_from_vwap_pct
    pullback_min_pct = _to_float(resolved_policy.pullback_min_pct)
    pullback_max_pct = _to_float(resolved_policy.pullback_max_pct)
    pullback_mature = pullback_depth_pct >= pullback_min_pct
    pullback_not_too_deep = pullback_depth_pct <= pullback_max_pct
    pullback_ok = pullback_mature and pullback_not_too_deep
    vwap_structure_ok = vwap_hold_ok or vwap_reclaim_ok
    confirmation_ok = volume_ok or rebound_ok or vwap_reclaim_ok

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
            "inferred_spacing_minutes": series_quality.get("inferred_spacing_minutes"),
            "series_class": series_quality.get("series_class"),
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
    if pullback_ok:
        signal_chain.append("pullback_structure")
    if confirmation_ok:
        signal_chain.append("confirmation_ready")
    if extension_ok:
        signal_chain.append("not_extended")

    playbook = str((frame or {}).get("playbook") or "").strip().lower()
    checks = {
        "breakout_ok": bool(breakout_ok),
        "vwap_hold_ok": bool(vwap_hold_ok),
        "vwap_reclaim_ok": bool(vwap_reclaim_ok),
        "vwap_structure_ok": bool(vwap_structure_ok),
        "volume_ok": bool(volume_ok),
        "rebound_ok": bool(rebound_ok),
        "confirmation_ok": bool(confirmation_ok),
        "extension_ok": bool(extension_ok),
        "pullback_mature": bool(pullback_mature),
        "pullback_not_too_deep": bool(pullback_not_too_deep),
        "pullback_structure_ok": bool(pullback_ok),
    }
    if playbook in ("pullback", "reversal"):
        relevant_checks = [
            "vwap_structure_ok",
            "pullback_mature",
            "pullback_not_too_deep",
            "extension_ok",
            "confirmation_ok",
            "vwap_reclaim_ok",
            "vwap_hold_ok",
            "rebound_ok",
            "volume_ok",
        ]
    else:
        relevant_checks = [
            "breakout_ok",
            "vwap_hold_ok",
            "volume_ok",
            "extension_ok",
            "rebound_ok",
            "pullback_structure_ok",
        ]
    passed_checks = [name for name in relevant_checks if checks.get(name)]
    failed_checks = [name for name in relevant_checks if not checks.get(name)]
    threshold_margins = {
        "volume_ratio": {
            "actual": volume_ratio,
            "min": _to_float(resolved_policy.volume_ratio_min),
            "distance_to_min": volume_ratio - _to_float(resolved_policy.volume_ratio_min),
        },
        "extended_from_vwap_pct": {
            "actual": extended_from_vwap_pct,
            "min": min_extended_from_vwap_pct,
            "max": max_extended_from_vwap_pct,
            "distance_to_min": extended_from_vwap_pct - min_extended_from_vwap_pct,
            "distance_to_max": max_extended_from_vwap_pct - extended_from_vwap_pct,
        },
        "pullback_depth_pct": {
            "actual": pullback_depth_pct,
            "min": pullback_min_pct,
            "max": pullback_max_pct,
            "distance_to_min": pullback_depth_pct - pullback_min_pct,
            "distance_to_max": pullback_max_pct - pullback_depth_pct,
        },
        "breakout_gap_pct": {
            "actual": ((current_close / recent_high) - 1.0) if recent_high > 0.0 and current_close > 0.0 else None,
            "min": breakout_buffer_pct,
            "distance_to_breakout": (current_close - breakout_level) if breakout_level > 0.0 else None,
        },
    }

    pattern = ""
    reason = ""
    triggered = False
    primary_failure_axis = ""
    if playbook in ("pullback", "reversal"):
        if vwap_structure_ok and pullback_ok and extension_ok and confirmation_ok:
            triggered = True
            if vwap_reclaim_ok and rebound_ok:
                pattern = "pullback_vwap_reclaim"
                reason = "pullback_reclaim_above_vwap_with_rebound_confirmation"
            elif rebound_ok:
                pattern = "pullback_rebound"
                reason = "pullback_rebound_above_vwap_with_confirmation"
            else:
                pattern = "pullback_vwap_hold"
                reason = "pullback_structure_above_vwap_with_confirmation"
        else:
            if not extension_ok:
                if extended_from_vwap_pct > max_extended_from_vwap_pct:
                    reason = "still_overextended_after_pullback"
                    primary_failure_axis = "overextension"
                else:
                    # Pullback setup is still too weak below VWAP band; wait for reclaim/structure.
                    reason = "pullback_below_vwap_reclaim_not_ready"
                    primary_failure_axis = "vwap_relationship"
            elif not pullback_mature:
                reason = "pullback_not_mature"
                primary_failure_axis = "pullback_structure"
            elif not pullback_not_too_deep:
                reason = "no_valid_pullback_structure"
                primary_failure_axis = "pullback_structure"
            elif not vwap_structure_ok:
                reason = "reclaim_not_confirmed"
                primary_failure_axis = "vwap_relationship"
            elif not confirmation_ok:
                reason = "volume_confirmation_missing"
                primary_failure_axis = "volume_confirmation"
            else:
                reason = "entry_signal_not_confirmed"
                primary_failure_axis = "entry_confirmation"
    else:
        if breakout_ok and vwap_hold_ok and volume_ok and extension_ok:
            triggered = True
            pattern = "breakout_vwap_hold"
            reason = "breakout_above_recent_high_with_vwap_hold_and_volume_confirmation"
        elif rebound_ok and vwap_hold_ok and volume_ok and pullback_ok and extension_ok:
            triggered = True
            pattern = "pullback_rebound"
            reason = "pullback_rebound_above_vwap_with_volume_confirmation"
        else:
            if not extension_ok:
                if extended_from_vwap_pct > max_extended_from_vwap_pct:
                    reason = "too_extended_from_vwap"
                    primary_failure_axis = "overextension"
                else:
                    reason = "below_vwap_reclaim_not_ready"
                    primary_failure_axis = "vwap_relationship"
            elif not breakout_ok and not rebound_ok:
                reason = "breakout_not_ready"
                primary_failure_axis = "breakout_readiness"
            elif not vwap_hold_ok:
                reason = "vwap_not_confirmed"
                primary_failure_axis = "vwap_relationship"
            elif not volume_ok:
                reason = "volume_insufficient"
                primary_failure_axis = "volume_confirmation"
            elif not pullback_ok:
                reason = "pullback_too_deep"
                primary_failure_axis = "pullback_structure"
            else:
                reason = "entry_signal_not_confirmed"
                primary_failure_axis = "entry_confirmation"

    if triggered and not primary_failure_axis:
        primary_failure_axis = "confirmed_entry"

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
        "pullback_mature": bool(pullback_mature),
        "pullback_not_too_deep": bool(pullback_not_too_deep),
        "confirmation_ok": bool(confirmation_ok),
        "vwap_structure_ok": bool(vwap_structure_ok),
        "engine_vwap_distance": (features or {}).get("engine_vwap_distance"),
        "engine_volume_spike20": (features or {}).get("engine_volume_spike20"),
        "engine_trend_strength": (features or {}).get("engine_trend_strength"),
        "inferred_spacing_minutes": series_quality.get("inferred_spacing_minutes"),
        "series_class": series_quality.get("series_class"),
    }
    out.update(
        {
            "triggered": bool(triggered),
            "decision": "BUY" if triggered else "WAIT",
            "pattern": pattern,
            "reason": reason,
            "signal_chain": signal_chain,
            "metrics": metrics,
            "passed_checks": passed_checks,
            "failed_checks": failed_checks,
            "primary_failure_axis": primary_failure_axis,
            "threshold_margins": threshold_margins,
        }
    )
    return out
