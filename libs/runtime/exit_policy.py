from __future__ import annotations

import os
from typing import Any, Dict, Optional


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clamp_non_negative(v: float) -> float:
    return float(v) if v > 0.0 else 0.0


def _to_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return bool(default)
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on")


def _build_chart_context_summary(policy: Dict[str, Any]) -> Dict[str, Any]:
    raw = policy.get("chart_context")
    chart_context = dict(raw) if isinstance(raw, dict) else {}
    features = chart_context.get("chart_structure_features")
    if not isinstance(features, dict):
        features = chart_context if chart_context else {}

    summary = {
        "available": False,
        "schema_version": str(features.get("schema_version") or "") if isinstance(features, dict) else "",
        "structure_hh_hl": None,
        "support_holding": None,
        "trend_regime": None,
        "ma_alignment_state": None,
        "failed_breakout": None,
        "momentum_follow_through": None,
        "structure_breakdown_signal": "",
        "notes": [],
    }
    if not isinstance(features, dict) or not bool(features):
        return summary

    structure = features.get("structure") if isinstance(features.get("structure"), dict) else {}
    trend_alignment = features.get("trend_alignment") if isinstance(features.get("trend_alignment"), dict) else {}
    support_resistance = (
        features.get("support_resistance") if isinstance(features.get("support_resistance"), dict) else {}
    )
    continuity_momentum = (
        features.get("continuity_momentum") if isinstance(features.get("continuity_momentum"), dict) else {}
    )

    summary["structure_hh_hl"] = structure.get("structure_hh_hl")
    summary["support_holding"] = support_resistance.get("support_holding")
    summary["trend_regime"] = trend_alignment.get("trend_regime")
    summary["ma_alignment_state"] = trend_alignment.get("ma_alignment_state")
    summary["failed_breakout"] = support_resistance.get("failed_breakout")
    summary["momentum_follow_through"] = continuity_momentum.get("momentum_follow_through")
    summary["available"] = bool(features.get("available"))
    summary["notes"] = [str(x or "").strip() for x in list(features.get("notes") or []) if str(x or "").strip()]

    if str(summary["failed_breakout"] or "").strip().lower() == "confirmed":
        summary["structure_breakdown_signal"] = "failed_breakout"
    elif str(summary["support_holding"] or "").strip().lower() == "lost":
        summary["structure_breakdown_signal"] = "support_lost"
    elif (
        str(summary["ma_alignment_state"] or "").strip().lower() == "bearish"
        and str(summary["trend_regime"] or "").strip().lower() in {"transition", "ranging"}
    ):
        summary["structure_breakdown_signal"] = "trend_alignment_breakdown"

    return summary


def apply_env_stop_take_fallbacks(policy: Dict[str, Any] | None) -> Dict[str, Any]:
    """Use env stop/take baselines only when policy does not already define them."""
    out = dict(policy or {})
    sl_raw = str(os.getenv("EXIT_POLICY_STOP_LOSS_PCT", "") or "").strip()
    tp_raw = str(os.getenv("EXIT_POLICY_TAKE_PROFIT_PCT", "") or "").strip()

    if sl_raw and _to_float(out.get("stop_loss_pct"), 0.0) <= 0.0:
        sl = _to_float(sl_raw, 0.03)
        out["stop_loss_pct"] = float(sl if sl > 0.0 else 0.03)

    if tp_raw and _to_float(out.get("take_profit_pct"), 0.0) <= 0.0:
        tp = _to_float(tp_raw, 0.05)
        out["take_profit_pct"] = float(tp if tp > 0.0 else 0.05)

    return out


def evaluate_exit_policy(
    *,
    price: Optional[float],
    avg_price: Optional[float],
    qty: int,
    hold_sec: Optional[int] = None,
    policy: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Evaluate stop-loss / take-profit exit policy for one position.

    Returns a deterministic decision payload. It never raises.
    """
    p = dict(policy or {})
    chart_context_summary = _build_chart_context_summary(p)
    out: Dict[str, Any] = {
        "evaluated": True,
        "triggered": False,
        "reason": "",
        "pnl_ratio": None,
        "chart_context_available": bool(chart_context_summary.get("available")),
        "chart_context_summary": dict(chart_context_summary),
        "structure_breakdown_signal": str(chart_context_summary.get("structure_breakdown_signal") or ""),
        "thresholds": {
            "hard_stop_pct": _clamp_non_negative(_to_float(p.get("hard_stop_pct"), 0.0)),
            "stop_loss_pct": _clamp_non_negative(_to_float(p.get("stop_loss_pct"), 0.03)),
            "take_profit_pct": _clamp_non_negative(_to_float(p.get("take_profit_pct"), 0.05)),
            "max_hold_sec": max(0, int(_to_float(p.get("max_hold_sec"), 0))),
            "time_stop_sec": max(
                0,
                int(
                    _to_float(
                        p.get("time_stop_sec"),
                        _to_float(p.get("max_hold_sec"), 0.0),
                    )
                ),
            ),
            "trailing_stop_pct": _clamp_non_negative(_to_float(p.get("trailing_stop_pct"), 0.0)),
            "vol_expansion_ratio": _clamp_non_negative(_to_float(p.get("vol_expansion_ratio"), 0.0)),
            "news_shock_threshold": _clamp_non_negative(_to_float(p.get("news_shock_threshold"), 0.0)),
            "peak_drawdown_exit_pct": _clamp_non_negative(_to_float(p.get("peak_drawdown_exit_pct"), 0.0)),
            "vwap_breakdown_pct": _clamp_non_negative(_to_float(p.get("vwap_breakdown_pct"), 0.0)),
            "intraday_low_break_pct": _clamp_non_negative(_to_float(p.get("intraday_low_break_pct"), 0.0)),
            "trend_strength_floor": _to_float(p.get("trend_strength_floor"), 0.0),
            "eod_flat_cutoff_min": max(0, int(_to_float(p.get("eod_flat_cutoff_min"), 10))),
        },
    }
    has_explicit_time_stop = "time_stop_sec" in p

    q = max(0, int(qty or 0))
    if q <= 0:
        out["reason"] = "no_position"
        return out

    emergency_halt = _to_bool(p.get("emergency_halt"), False)
    if emergency_halt:
        out["triggered"] = True
        out["reason"] = "emergency_halt"
        return out

    use_eod_flat = _to_bool(p.get("use_eod_flat"), False)
    minutes_to_close = _to_float(p.get("minutes_to_close"), -1.0)
    eod_cutoff = int(out["thresholds"]["eod_flat_cutoff_min"])
    if use_eod_flat and minutes_to_close >= 0.0 and minutes_to_close <= float(eod_cutoff):
        out["triggered"] = True
        out["reason"] = "eod_flat"
        out["minutes_to_close"] = float(minutes_to_close)
        return out

    max_hold_sec = int(out["thresholds"]["max_hold_sec"])
    time_stop_sec = int(out["thresholds"]["time_stop_sec"])
    hold_limit = time_stop_sec if time_stop_sec > 0 else max_hold_sec
    hs = None if hold_sec is None else max(0, int(hold_sec))
    out["hold_sec"] = hs
    if hold_limit > 0 and hs is not None and hs >= hold_limit:
        out["triggered"] = True
        out["reason"] = "time_stop" if has_explicit_time_stop and time_stop_sec > 0 else "max_hold"
        return out

    # News shock exit (optional): sentiment crash forces immediate flattening.
    news_shock_th = float(out["thresholds"]["news_shock_threshold"])
    if news_shock_th > 0.0:
        symbol_sent = _to_float(p.get("symbol_sentiment_score"), 0.0)
        global_sent = _to_float(p.get("global_sentiment_score"), 0.0)
        out["symbol_sentiment_score"] = float(symbol_sent)
        out["global_sentiment_score"] = float(global_sent)
        if symbol_sent <= -news_shock_th or global_sent <= -news_shock_th:
            out["triggered"] = True
            out["reason"] = "news_shock"
            return out

    px = _to_float(price, 0.0) if price is not None else 0.0
    apx = _to_float(avg_price, 0.0) if avg_price is not None else 0.0
    if px <= 0.0 or apx <= 0.0:
        out["reason"] = "price_unavailable"
        return out

    # Volatility expansion stop (optional).
    vol_ratio_th = float(out["thresholds"]["vol_expansion_ratio"])
    if vol_ratio_th > 0.0:
        current_vol = _to_float(p.get("current_volatility"), 0.0)
        baseline_vol = _to_float(p.get("baseline_volatility"), 0.0)
        if baseline_vol > 0.0 and current_vol > 0.0:
            vol_ratio = float(current_vol / baseline_vol)
            out["volatility_ratio"] = vol_ratio
            if vol_ratio >= vol_ratio_th:
                out["triggered"] = True
                out["reason"] = "volatility_expansion"
                return out

    pnl_ratio = float((px / apx) - 1.0)
    out["pnl_ratio"] = pnl_ratio

    sl = float(out["thresholds"]["stop_loss_pct"])
    hard_sl = float(out["thresholds"]["hard_stop_pct"])
    tp = float(out["thresholds"]["take_profit_pct"])

    effective_stop_candidates = [
        (reason, threshold)
        for reason, threshold in (
            ("hard_stop", hard_sl),
            ("stop_loss", sl),
        )
        if threshold > 0.0
    ]
    effective_stop_reason = ""
    effective_stop_pct = 0.0
    if effective_stop_candidates:
        effective_stop_reason, effective_stop_pct = min(
            effective_stop_candidates,
            key=lambda row: float(row[1]),
        )
        out["thresholds"]["effective_stop_loss_pct"] = float(effective_stop_pct)
        out["thresholds"]["effective_stop_reason"] = str(effective_stop_reason)
    else:
        out["thresholds"]["effective_stop_loss_pct"] = 0.0
        out["thresholds"]["effective_stop_reason"] = ""

    if effective_stop_pct > 0.0 and pnl_ratio <= -effective_stop_pct:
        out["triggered"] = True
        out["reason"] = str(effective_stop_reason or "stop_loss")
        return out

    if tp > 0.0 and pnl_ratio >= tp:
        out["triggered"] = True
        out["reason"] = "take_profit"
        return out

    peak_price = _to_float(p.get("peak_price"), 0.0)
    if peak_price <= 0.0:
        peak_price = max(apx, px)
    if peak_price > 0.0:
        peak_drawdown = float((px / peak_price) - 1.0)
        out["peak_drawdown"] = peak_drawdown
        peak_drawdown_th = float(out["thresholds"]["peak_drawdown_exit_pct"])
        if peak_drawdown_th > 0.0 and peak_price > apx and peak_drawdown <= -peak_drawdown_th:
            out["triggered"] = True
            out["reason"] = "peak_drawdown"
            return out

    vwap_breakdown_th = float(out["thresholds"]["vwap_breakdown_pct"])
    if vwap_breakdown_th > 0.0:
        vwap_distance = _to_float(p.get("vwap_distance"), 0.0)
        out["vwap_distance"] = float(vwap_distance)
        require_profit = _to_bool(p.get("vwap_break_requires_profit"), True)
        if vwap_distance <= -vwap_breakdown_th and (not require_profit or peak_price > apx or pnl_ratio > 0.0):
            out["triggered"] = True
            out["reason"] = "vwap_breakdown"
            return out

    intraday_low_break_pct = float(out["thresholds"]["intraday_low_break_pct"])
    if intraday_low_break_pct > 0.0:
        prior_bar_low = _to_float(p.get("prior_bar_low"), 0.0)
        out["prior_bar_low"] = float(prior_bar_low)
        if prior_bar_low > 0.0 and px <= float(prior_bar_low * (1.0 - intraday_low_break_pct)):
            out["triggered"] = True
            out["reason"] = "intraday_low_break"
            return out

    trend_strength_floor = float(out["thresholds"]["trend_strength_floor"])
    if trend_strength_floor != 0.0:
        trend_strength = _to_float(p.get("trend_strength"), 0.0)
        out["trend_strength"] = float(trend_strength)
        vwap_distance = _to_float(p.get("vwap_distance"), out.get("vwap_distance") or 0.0)
        out["vwap_distance"] = float(vwap_distance)
        if trend_strength <= trend_strength_floor and vwap_distance < 0.0:
            out["triggered"] = True
            out["reason"] = "trend_breakdown"
            return out

    # Trailing stop (optional).
    trail = float(out["thresholds"]["trailing_stop_pct"])
    if trail > 0.0:
        if peak_price > 0.0:
            drawdown = float((px / peak_price) - 1.0)
            out["trailing_drawdown"] = drawdown
            if drawdown <= -trail:
                out["triggered"] = True
                out["reason"] = "trailing_stop"
                return out

    out["reason"] = "hold"
    return out
