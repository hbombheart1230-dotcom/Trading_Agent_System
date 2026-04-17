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


def _to_ratio(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        out = float(v)
    except Exception:
        return None
    if abs(out) > 1.0:
        out = out / 100.0
    return float(out)


def apply_account_pnl_crosscheck_context(
    policy: Dict[str, Any] | None,
    *,
    position: Dict[str, Any] | None,
) -> Dict[str, Any]:
    """Attach authoritative account fields used for exit PnL cross-checking.

    The caller keeps ownership of how positions are sourced. This helper only
    normalizes a few optional fields so exit evaluation can reconcile
    raw/live-price PnL with account-authoritative unrealized PnL.
    """
    out = dict(policy or {})
    if not isinstance(position, dict):
        return out

    qty = max(0, int(_to_float(position.get("qty"), 0.0)))
    avg_price = _to_float(position.get("avg_price"), 0.0)
    if qty > 0 and out.get("account_qty") in (None, ""):
        out["account_qty"] = int(qty)
    if avg_price > 0.0 and out.get("account_avg_price") in (None, ""):
        out["account_avg_price"] = float(avg_price)

    for key in ("price", "cur_price", "last_price", "current_price"):
        raw = position.get(key)
        if raw in (None, ""):
            continue
        px = _to_float(raw, 0.0)
        if px > 0.0 and out.get("account_current_price") in (None, ""):
            out["account_current_price"] = float(px)
            out.setdefault("account_current_price_source", f"position.{key}")
            break

    unrealized = position.get("unrealized_pnl")
    if unrealized not in (None, "") and out.get("account_unrealized_pnl") in (None, ""):
        out["account_unrealized_pnl"] = float(_to_float(unrealized, 0.0))
    ratio = _to_ratio(
        position.get("account_pnl_ratio")
        if position.get("account_pnl_ratio") not in (None, "")
        else position.get("unrealized_pnl_rate")
    )
    if ratio is not None and out.get("account_pnl_ratio") in (None, ""):
        out["account_pnl_ratio"] = float(ratio)
        out.setdefault(
            "account_pnl_ratio_source",
            str(position.get("account_pnl_ratio_source") or "position.account_pnl_ratio"),
        )

    out.setdefault("account_crosscheck_mode", "conservative")
    return out


def _build_account_pnl_crosscheck(
    policy: Dict[str, Any],
    *,
    price: Optional[float],
    avg_price: Optional[float],
    qty: int,
) -> Dict[str, Any]:
    q = max(0, int(qty or 0))
    raw_price = _to_float(price, 0.0) if price is not None else 0.0
    avg = _to_float(avg_price, 0.0) if avg_price is not None else 0.0
    raw_pnl_ratio = float((raw_price / avg) - 1.0) if raw_price > 0.0 and avg > 0.0 else None

    account_qty_raw = policy.get("account_qty")
    account_qty = max(0, int(_to_float(account_qty_raw, float(q)))) if account_qty_raw not in (None, "") else q
    account_avg_raw = policy.get("account_avg_price")
    account_avg = _to_float(account_avg_raw, avg) if account_avg_raw not in (None, "") else avg
    account_current_price = None
    if policy.get("account_current_price") not in (None, ""):
        px = _to_float(policy.get("account_current_price"), 0.0)
        if px > 0.0:
            account_current_price = float(px)
    account_pnl_ratio = _to_ratio(policy.get("account_pnl_ratio"))
    account_pnl_ratio_source = str(policy.get("account_pnl_ratio_source") or "")

    account_unrealized_pnl = None
    if policy.get("account_unrealized_pnl") not in (None, ""):
        account_unrealized_pnl = float(_to_float(policy.get("account_unrealized_pnl"), 0.0))

    account_ratio_mark_price = None
    if account_pnl_ratio is not None and account_avg > 0.0:
        account_mark = float(account_avg * (1.0 + float(account_pnl_ratio)))
        if account_mark > 0.0:
            account_ratio_mark_price = float(account_mark)

    account_unrealized_mark_price = None
    if account_unrealized_pnl is not None and account_qty > 0 and account_avg > 0.0:
        account_mark = account_avg + (account_unrealized_pnl / float(account_qty))
        if account_mark > 0.0:
            account_unrealized_mark_price = float(account_mark)
        notional = float(account_avg * float(account_qty))
        if notional > 0.0 and account_pnl_ratio is None:
            account_pnl_ratio = float(account_unrealized_pnl / notional)
            if not account_pnl_ratio_source:
                account_pnl_ratio_source = "account_unrealized_pnl"

    reference_price = 0.0
    if raw_price > 0.0:
        reference_price = float(raw_price)
    elif account_current_price is not None and account_current_price > 0.0:
        reference_price = float(account_current_price)

    def _price_ratio(candidate: Optional[float]) -> float | None:
        if candidate is None or candidate <= 0.0 or reference_price <= 0.0:
            return None
        return float(candidate / reference_price)

    def _price_anomaly_reason(candidate: Optional[float], *, source: str) -> str:
        ratio = _price_ratio(candidate)
        if ratio is None:
            return ""
        if ratio < 0.5:
            return f"{source}_below_reference_ratio:{ratio:.4f}"
        if ratio > 1.5:
            return f"{source}_above_reference_ratio:{ratio:.4f}"
        return ""

    ratio_mark_anomaly_reason = _price_anomaly_reason(account_ratio_mark_price, source="account_pnl_ratio_mark")
    unrealized_mark_anomaly_reason = _price_anomaly_reason(
        account_unrealized_mark_price,
        source="account_unrealized_mark",
    )

    account_mark_price = None
    account_mark_price_source = ""
    price_anomaly_flag = False
    price_anomaly_reason = ""
    pnl_fallback_applied = False
    fallback_price_source = ""

    if account_ratio_mark_price is not None and not ratio_mark_anomaly_reason:
        account_mark_price = float(account_ratio_mark_price)
        account_mark_price_source = "account_pnl_ratio_mark"
    elif account_unrealized_mark_price is not None and not unrealized_mark_anomaly_reason:
        account_mark_price = float(account_unrealized_mark_price)
        account_mark_price_source = "account_unrealized_mark"
        if account_ratio_mark_price is not None and bool(ratio_mark_anomaly_reason):
            price_anomaly_flag = True
            price_anomaly_reason = str(ratio_mark_anomaly_reason)
            pnl_fallback_applied = True
            fallback_price_source = "account_unrealized_mark"
    elif account_ratio_mark_price is not None and bool(ratio_mark_anomaly_reason):
        price_anomaly_flag = True
        price_anomaly_reason = str(ratio_mark_anomaly_reason)
        pnl_fallback_applied = True
        fallback_price_source = "raw_price" if raw_price > 0.0 else "account_current_price"
    elif account_unrealized_mark_price is not None and bool(unrealized_mark_anomaly_reason):
        price_anomaly_flag = True
        price_anomaly_reason = str(unrealized_mark_anomaly_reason)
        pnl_fallback_applied = True
        fallback_price_source = "raw_price" if raw_price > 0.0 else "account_current_price"

    effective_price = None
    effective_source = "unavailable"
    applied = False
    reason = "unavailable"

    if raw_price > 0.0:
        effective_price = float(raw_price)
        effective_source = "raw_price"
        reason = "raw_price_only"

    if account_mark_price is not None and account_mark_price > 0.0:
        if effective_price is None or effective_price <= 0.0:
            effective_price = float(account_mark_price)
            effective_source = str(account_mark_price_source or "account_unrealized_mark")
            applied = True
            reason = "account_mark_fallback" if not pnl_fallback_applied else f"price_anomaly_fallback:{effective_source}"
        elif str(policy.get("account_crosscheck_mode") or "conservative").strip().lower() == "conservative":
            if account_mark_price < effective_price - 1e-9:
                effective_price = float(account_mark_price)
                effective_source = str(account_mark_price_source or "account_unrealized_mark")
                applied = True
                if effective_source == "account_pnl_ratio_mark":
                    reason = "account_pnl_ratio_more_conservative"
                elif pnl_fallback_applied:
                    reason = f"price_anomaly_fallback:{effective_source}"
                else:
                    reason = "account_unrealized_pnl_more_conservative"
            elif raw_pnl_ratio is not None and account_pnl_ratio is not None:
                gap = float(account_pnl_ratio - raw_pnl_ratio)
                if abs(gap) <= 1e-6:
                    reason = "aligned"
                else:
                    reason = "account_mark_higher_than_raw_price"
    elif pnl_fallback_applied and effective_price is not None and effective_price > 0.0:
        effective_source = str(fallback_price_source or effective_source)
        reason = f"price_anomaly_fallback:{effective_source}"

    if (
        pnl_fallback_applied
        and account_mark_price is not None
        and effective_price is not None
        and abs(float(account_mark_price) - float(effective_price)) <= 1e-9
    ):
        effective_source = str(account_mark_price_source or effective_source)
        applied = True
        reason = f"price_anomaly_fallback:{effective_source}"

    effective_pnl_ratio = None
    if effective_price is not None and effective_price > 0.0 and avg > 0.0:
        effective_pnl_ratio = float((effective_price / avg) - 1.0)

    pnl_ratio_gap = None
    if raw_pnl_ratio is not None and account_pnl_ratio is not None:
        pnl_ratio_gap = float(account_pnl_ratio - raw_pnl_ratio)

    price_gap = None
    if account_mark_price is not None and raw_price > 0.0:
        price_gap = float(account_mark_price - raw_price)

    return {
        "available": bool(raw_pnl_ratio is not None or account_pnl_ratio is not None),
        "mode": str(policy.get("account_crosscheck_mode") or "conservative"),
        "raw_price": float(raw_price) if raw_price > 0.0 else None,
        "raw_pnl_ratio": raw_pnl_ratio,
        "account_current_price": account_current_price,
        "account_current_price_source": str(policy.get("account_current_price_source") or ""),
        "account_unrealized_pnl": account_unrealized_pnl,
        "account_mark_price": account_mark_price,
        "account_mark_price_source": account_mark_price_source,
        "account_ratio_mark_price": account_ratio_mark_price,
        "account_unrealized_mark_price": account_unrealized_mark_price,
        "account_pnl_ratio": account_pnl_ratio,
        "account_pnl_ratio_source": account_pnl_ratio_source,
        "effective_price": effective_price,
        "effective_price_source": effective_source,
        "effective_pnl_ratio": effective_pnl_ratio,
        "pnl_ratio_gap": pnl_ratio_gap,
        "price_gap": price_gap,
        "applied": bool(applied),
        "reason": reason,
        "price_anomaly_flag": bool(price_anomaly_flag),
        "price_anomaly_reason": str(price_anomaly_reason),
        "pnl_fallback_applied": bool(pnl_fallback_applied),
        "fallback_price_source": str(fallback_price_source),
    }


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
        "hold_block_reason": "",
        "max_runup_pct": None,
        "peak_drawdown_from_peak": None,
        "peak_drawdown_armed": False,
        "peak_drawdown_mode": "",
        "final_peak_drawdown_ratio": None,
        "peak_drawdown_source": "",
        "exit_trigger_metric_name": "",
        "exit_trigger_metric_value": None,
        "exit_trigger_metric_source": "",
        "pnl_ratio": None,
        "raw_pnl_ratio": None,
        "effective_pnl_ratio": None,
        "raw_price": None,
        "effective_price": None,
        "effective_price_source": "",
        "account_current_price": None,
        "account_current_price_source": "",
        "account_unrealized_pnl": None,
        "account_mark_price": None,
        "account_mark_price_source": "",
        "account_pnl_ratio": None,
        "account_pnl_ratio_source": "",
        "pnl_crosscheck_gap": None,
        "price_crosscheck_gap": None,
        "pnl_crosscheck_applied": False,
        "pnl_crosscheck_reason": "",
        "price_anomaly_flag": False,
        "price_anomaly_reason": "",
        "pnl_fallback_applied": False,
        "fallback_price_source": "",
        "account_crosscheck": {},
        "chart_context_available": bool(chart_context_summary.get("available")),
        "chart_context_summary": dict(chart_context_summary),
        "structure_breakdown_signal": str(chart_context_summary.get("structure_breakdown_signal") or ""),
        "exit_threshold_source": str(
            p.get("final_exit_threshold_source")
            or p.get("policy_source")
            or p.get("effective_policy_source")
            or "effective_policy"
        ),
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
            "profit_protection_activation_pct": _clamp_non_negative(
                _to_float(
                    p.get(
                        "profit_protection_activation_pct",
                        p.get("peak_drawdown_activation_pct", 0.008),
                    ),
                    0.008,
                )
            ),
            "peak_drawdown_mode": str(p.get("peak_drawdown_mode") or "profit_protection").strip().lower(),
            "vwap_breakdown_pct": _clamp_non_negative(_to_float(p.get("vwap_breakdown_pct"), 0.0)),
            "intraday_low_break_pct": _clamp_non_negative(_to_float(p.get("intraday_low_break_pct"), 0.0)),
            "trend_strength_floor": _to_float(p.get("trend_strength_floor"), 0.0),
            "eod_flat_cutoff_min": max(0, int(_to_float(p.get("eod_flat_cutoff_min"), 10))),
        },
    }
    out["peak_drawdown_mode"] = str(out["thresholds"].get("peak_drawdown_mode") or "profit_protection")

    def _finalize(
        triggered: bool | None = None,
        reason: str | None = None,
        *,
        metric_name: str = "",
        metric_value: Any = None,
        metric_source: str = "",
    ) -> Dict[str, Any]:
        if triggered is not None:
            out["triggered"] = bool(triggered)
        if reason is not None:
            out["reason"] = str(reason or "")
        final_reason = str(out.get("reason") or "")
        inferred_metric_name = str(metric_name or "")
        inferred_metric_value = metric_value
        inferred_metric_source = str(metric_source or "")
        if not inferred_metric_name and final_reason in {"hard_stop", "stop_loss", "take_profit"}:
            inferred_metric_name = "effective_pnl_ratio"
            inferred_metric_value = out.get("effective_pnl_ratio")
            inferred_metric_source = "effective_pnl_ratio"
        elif not inferred_metric_name and final_reason == "peak_drawdown":
            inferred_metric_name = "peak_drawdown_ratio"
            inferred_metric_value = out.get("final_peak_drawdown_ratio")
            inferred_metric_source = str(out.get("peak_drawdown_source") or "effective_price_vs_peak_price")
        elif not inferred_metric_name and final_reason == "vwap_breakdown":
            inferred_metric_name = "vwap_distance"
            inferred_metric_value = out.get("vwap_distance")
            inferred_metric_source = "selected.features.engine_vwap_distance"
        elif not inferred_metric_name and final_reason == "trend_breakdown":
            inferred_metric_name = "trend_strength"
            inferred_metric_value = out.get("trend_strength")
            inferred_metric_source = "selected.features.engine_trend_strength"
        elif not inferred_metric_name and final_reason == "volatility_expansion":
            inferred_metric_name = "volatility_ratio"
            inferred_metric_value = out.get("volatility_ratio")
            inferred_metric_source = "current_volatility_vs_baseline"
        elif not inferred_metric_name and final_reason == "eod_flat":
            inferred_metric_name = "minutes_to_close"
            inferred_metric_value = out.get("minutes_to_close")
            inferred_metric_source = "session_clock"
        out["exit_trigger_metric_name"] = inferred_metric_name
        out["exit_trigger_metric_value"] = inferred_metric_value
        out["exit_trigger_metric_source"] = inferred_metric_source
        out["final_exit_thresholds"] = dict(out.get("thresholds") or {})
        return out

    has_explicit_time_stop = "time_stop_sec" in p

    q = max(0, int(qty or 0))
    if q <= 0:
        return _finalize(reason="no_position")

    emergency_halt = _to_bool(p.get("emergency_halt"), False)
    if emergency_halt:
        return _finalize(triggered=True, reason="emergency_halt")

    use_eod_flat = _to_bool(p.get("use_eod_flat"), False)
    minutes_to_close = _to_float(p.get("minutes_to_close"), -1.0)
    eod_cutoff = int(out["thresholds"]["eod_flat_cutoff_min"])
    if use_eod_flat and minutes_to_close >= 0.0 and minutes_to_close <= float(eod_cutoff):
        out["minutes_to_close"] = float(minutes_to_close)
        return _finalize(triggered=True, reason="eod_flat")

    max_hold_sec = int(out["thresholds"]["max_hold_sec"])
    time_stop_sec = int(out["thresholds"]["time_stop_sec"])
    hold_limit = time_stop_sec if time_stop_sec > 0 else max_hold_sec
    hs = None if hold_sec is None else max(0, int(hold_sec))
    out["hold_sec"] = hs
    if hold_limit > 0 and hs is not None and hs >= hold_limit:
        return _finalize(
            triggered=True,
            reason="time_stop" if has_explicit_time_stop and time_stop_sec > 0 else "max_hold",
        )

    # News shock exit (optional): sentiment crash forces immediate flattening.
    news_shock_th = float(out["thresholds"]["news_shock_threshold"])
    if news_shock_th > 0.0:
        symbol_sent = _to_float(p.get("symbol_sentiment_score"), 0.0)
        global_sent = _to_float(p.get("global_sentiment_score"), 0.0)
        out["symbol_sentiment_score"] = float(symbol_sent)
        out["global_sentiment_score"] = float(global_sent)
        if symbol_sent <= -news_shock_th or global_sent <= -news_shock_th:
            return _finalize(triggered=True, reason="news_shock")

    apx = _to_float(avg_price, 0.0) if avg_price is not None else 0.0
    crosscheck = _build_account_pnl_crosscheck(
        p,
        price=price,
        avg_price=avg_price,
        qty=q,
    )
    out["account_crosscheck"] = dict(crosscheck)
    out["raw_price"] = crosscheck.get("raw_price")
    out["effective_price"] = crosscheck.get("effective_price")
    out["effective_price_source"] = str(crosscheck.get("effective_price_source") or "")
    out["account_current_price"] = crosscheck.get("account_current_price")
    out["account_current_price_source"] = str(crosscheck.get("account_current_price_source") or "")
    out["account_unrealized_pnl"] = crosscheck.get("account_unrealized_pnl")
    out["account_mark_price"] = crosscheck.get("account_mark_price")
    out["account_mark_price_source"] = str(crosscheck.get("account_mark_price_source") or "")
    out["account_pnl_ratio"] = crosscheck.get("account_pnl_ratio")
    out["account_pnl_ratio_source"] = str(crosscheck.get("account_pnl_ratio_source") or "")
    out["raw_pnl_ratio"] = crosscheck.get("raw_pnl_ratio")
    out["effective_pnl_ratio"] = crosscheck.get("effective_pnl_ratio")
    out["pnl_crosscheck_gap"] = crosscheck.get("pnl_ratio_gap")
    out["price_crosscheck_gap"] = crosscheck.get("price_gap")
    out["pnl_crosscheck_applied"] = bool(crosscheck.get("applied"))
    out["pnl_crosscheck_reason"] = str(crosscheck.get("reason") or "")
    out["price_anomaly_flag"] = bool(crosscheck.get("price_anomaly_flag"))
    out["price_anomaly_reason"] = str(crosscheck.get("price_anomaly_reason") or "")
    out["pnl_fallback_applied"] = bool(crosscheck.get("pnl_fallback_applied"))
    out["fallback_price_source"] = str(crosscheck.get("fallback_price_source") or "")

    px = _to_float(crosscheck.get("effective_price"), 0.0) if crosscheck.get("effective_price") is not None else 0.0
    if px <= 0.0 or apx <= 0.0:
        if out["price_anomaly_flag"] and not out["hold_block_reason"]:
            out["hold_block_reason"] = str(out["price_anomaly_reason"] or "price_anomaly")
        return _finalize(reason="price_unavailable")

    # Volatility expansion stop (optional).
    vol_ratio_th = float(out["thresholds"]["vol_expansion_ratio"])
    if vol_ratio_th > 0.0:
        current_vol = _to_float(p.get("current_volatility"), 0.0)
        baseline_vol = _to_float(p.get("baseline_volatility"), 0.0)
        if baseline_vol > 0.0 and current_vol > 0.0:
            vol_ratio = float(current_vol / baseline_vol)
            out["volatility_ratio"] = vol_ratio
            if vol_ratio >= vol_ratio_th:
                return _finalize(triggered=True, reason="volatility_expansion")

    pnl_ratio = float((px / apx) - 1.0)
    out["pnl_ratio"] = pnl_ratio
    out["effective_pnl_ratio"] = pnl_ratio

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
        return _finalize(triggered=True, reason=str(effective_stop_reason or "stop_loss"))

    if tp > 0.0 and pnl_ratio >= tp:
        return _finalize(triggered=True, reason="take_profit")

    peak_price = _to_float(p.get("peak_price"), 0.0)
    if peak_price <= 0.0:
        peak_price = max(apx, px)
    if peak_price > 0.0:
        max_runup_pct = float((peak_price / apx) - 1.0) if apx > 0.0 else 0.0
        peak_drawdown = float((px / peak_price) - 1.0)
        peak_drawdown_mode = str(out["thresholds"].get("peak_drawdown_mode") or "profit_protection").strip().lower()
        if not peak_drawdown_mode:
            peak_drawdown_mode = "profit_protection"
        activation_pct = float(out["thresholds"].get("profit_protection_activation_pct") or 0.0)
        if peak_drawdown_mode in {"disabled", "off", "none"}:
            peak_drawdown_armed = False
        elif peak_drawdown_mode in {"profit_protection", "profit-protection"}:
            peak_drawdown_armed = bool(max_runup_pct >= activation_pct)
        else:
            # Backward-compatible fallback for unknown/legacy modes.
            peak_drawdown_armed = True
        out["max_runup_pct"] = max_runup_pct
        out["peak_drawdown"] = peak_drawdown
        out["peak_drawdown_from_peak"] = peak_drawdown
        out["peak_drawdown_armed"] = bool(peak_drawdown_armed)
        out["peak_drawdown_mode"] = str(peak_drawdown_mode)
        out["final_peak_drawdown_ratio"] = peak_drawdown
        out["peak_drawdown_source"] = "effective_price_vs_peak_price"
        peak_drawdown_th = float(out["thresholds"]["peak_drawdown_exit_pct"])
        if peak_drawdown_th > 0.0 and peak_drawdown_armed and peak_drawdown <= -peak_drawdown_th:
            return _finalize(
                triggered=True,
                reason="peak_drawdown",
                metric_name="peak_drawdown_ratio",
                metric_value=peak_drawdown,
                metric_source="effective_price_vs_peak_price",
            )

    vwap_breakdown_th = float(out["thresholds"]["vwap_breakdown_pct"])
    if vwap_breakdown_th > 0.0:
        vwap_distance = _to_float(p.get("vwap_distance"), 0.0)
        out["vwap_distance"] = float(vwap_distance)
        require_profit = _to_bool(p.get("vwap_break_requires_profit"), True)
        if vwap_distance <= -vwap_breakdown_th and (not require_profit or peak_price > apx or pnl_ratio > 0.0):
            return _finalize(triggered=True, reason="vwap_breakdown")

    intraday_low_break_pct = float(out["thresholds"]["intraday_low_break_pct"])
    if intraday_low_break_pct > 0.0:
        prior_bar_low = _to_float(p.get("prior_bar_low"), 0.0)
        out["prior_bar_low"] = float(prior_bar_low)
        if prior_bar_low > 0.0 and px <= float(prior_bar_low * (1.0 - intraday_low_break_pct)):
            return _finalize(triggered=True, reason="intraday_low_break")

    trend_strength_floor = float(out["thresholds"]["trend_strength_floor"])
    if trend_strength_floor != 0.0:
        trend_strength = _to_float(p.get("trend_strength"), 0.0)
        out["trend_strength"] = float(trend_strength)
        vwap_distance = _to_float(p.get("vwap_distance"), out.get("vwap_distance") or 0.0)
        out["vwap_distance"] = float(vwap_distance)
        if trend_strength <= trend_strength_floor and vwap_distance < 0.0:
            return _finalize(triggered=True, reason="trend_breakdown")

    # Trailing stop (optional).
    trail = float(out["thresholds"]["trailing_stop_pct"])
    if trail > 0.0:
        if peak_price > 0.0:
            drawdown = float((px / peak_price) - 1.0)
            out["trailing_drawdown"] = drawdown
            if drawdown <= -trail:
                return _finalize(triggered=True, reason="trailing_stop")

    if out["price_anomaly_flag"] and not out["hold_block_reason"]:
        out["hold_block_reason"] = f"price_anomaly_fallback:{str(out.get('price_anomaly_reason') or '')}".strip(":")
    return _finalize(reason="hold")
