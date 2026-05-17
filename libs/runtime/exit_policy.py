from __future__ import annotations

import os
import re
from typing import Any, Dict, Optional

from libs.runtime.etf_deviation import (
    DEFAULT_PREMIUM_TRIGGER_PCT,
    normalize_deviation_pct,
    score_etf_deviation_for_exit,
)


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


def _to_float_list(v: Any) -> list[float]:
    raw_items: list[Any]
    if isinstance(v, (list, tuple)):
        raw_items = list(v)
    elif isinstance(v, str):
        raw_items = re.split(r"[,;|]\s*", v.strip()) if v.strip() else []
    else:
        raw_items = []
    out: list[float] = []
    for item in raw_items:
        x = _to_float(item, 0.0)
        if x > 0.0:
            out.append(float(x))
    return sorted(set(out))


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
        "peak_drawdown_blocked": False,
        "peak_drawdown_block_reason": "",
        "peak_drawdown_profit_floor_required_pct": None,
        "peak_drawdown_profit_floor_met": False,
        "peak_drawdown_profit_protection_urgent": False,
        "peak_drawdown_profit_protection_reason": "",
        "final_peak_drawdown_ratio": None,
        "peak_drawdown_source": "",
        "risk_reward_take_profit_target_pct": None,
        "resistance_price": None,
        "resistance_price_source": "",
        "resistance_distance_pct": None,
        "profit_time_stop_peak_giveback_pct": None,
        "partial_exit": False,
        "exit_qty": None,
        "exit_qty_fraction": None,
        "partial_take_profit_taken": False,
        "profit_ladder_level_pct": None,
        "profit_ladder_level_index": None,
        "risk_reward_take_profit_rung": None,
        "volume_ratio": None,
        "execution_strength": None,
        "trade_strength": None,
        "opening_gap_chase_observed": False,
        "etf_deviation_pct": None,
        "etf_deviation_source": "",
        "etf_premium_take_profit_score": 0.0,
        "etf_premium_take_profit_armed": False,
        "exit_trigger_metric_name": "",
        "exit_trigger_metric_value": None,
        "exit_trigger_metric_source": "",
        "vwap_breakdown_confirmation_required": False,
        "vwap_breakdown_confirmed": False,
        "vwap_breakdown_confirmation_pending": False,
        "vwap_breakdown_confirmation_reason": "",
        "vwap_breakdown_consecutive_bars": 0,
        "vwap_breakdown_low_break_confirmed": False,
        "vwap_breakdown_volume_confirmed": False,
        "protective_exit_floor_blocked": False,
        "protective_exit_floor_blocked_reason": "",
        "protective_exit_hard_invalidation": False,
        "protective_exit_hard_invalidation_reason": "",
        "protective_exit_hard_invalidation_suppressed_by_cost_floor": False,
        "protective_exit_hard_invalidation_suppressed_reason": "",
        "pnl_ratio": None,
        "raw_pnl_ratio": None,
        "gross_pnl_ratio": None,
        "technical_pnl_ratio": None,
        "effective_pnl_ratio": None,
        "stop_pnl_ratio": None,
        "stop_pnl_ratio_source": "",
        "hard_stop_pnl_ratio": None,
        "hard_stop_pnl_ratio_source": "",
        "cost_drag_pressure": False,
        "cost_drag_pressure_pct": None,
        "cost_drag_pressure_reason": "",
        "stop_loss_cost_drag_blocked": False,
        "stop_loss_cost_drag_blocked_reason": "",
        "expected_exit_price": None,
        "expected_exit_price_source": "",
        "expected_exit_price_fallback_used": False,
        "expected_exit_slippage_buffer_pct": None,
        "expected_exit_pnl_ratio": None,
        "expected_exit_net_pnl_ratio": None,
        "expected_exit_profit_floor_met": False,
        "expected_exit_profit_floor_gap_pct": None,
        "expected_exit_profit_floor_blocked": False,
        "expected_exit_profit_floor_blocked_reason": "",
        "raw_price": None,
        "technical_price": None,
        "technical_price_source": "",
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
            "partial_take_profit_pct": _clamp_non_negative(_to_float(p.get("partial_take_profit_pct"), 0.0)),
            "partial_take_profit_fraction": _clamp_non_negative(
                _to_float(p.get("partial_take_profit_fraction"), 0.0)
            ),
            "profit_ladder_levels_pct": _to_float_list(p.get("profit_ladder_levels_pct")),
            "profit_ladder_fraction": _clamp_non_negative(_to_float(p.get("profit_ladder_fraction"), 0.0)),
            "risk_reward_take_profit_r": _clamp_non_negative(_to_float(p.get("risk_reward_take_profit_r"), 0.0)),
            "risk_reward_take_profit_rungs": _to_float_list(p.get("risk_reward_take_profit_rungs")),
            "risk_reward_take_profit_fraction": _clamp_non_negative(
                _to_float(p.get("risk_reward_take_profit_fraction"), 0.0)
            ),
            "risk_reward_take_profit_min_pct": _clamp_non_negative(
                _to_float(p.get("risk_reward_take_profit_min_pct"), 0.0)
            ),
            "vwap_extension_take_profit_pct": _clamp_non_negative(
                _to_float(p.get("vwap_extension_take_profit_pct"), 0.0)
            ),
            "vwap_extension_take_profit_min_pct": _clamp_non_negative(
                _to_float(p.get("vwap_extension_take_profit_min_pct"), 0.0)
            ),
            "resistance_take_profit_near_pct": _clamp_non_negative(
                _to_float(p.get("resistance_take_profit_near_pct"), 0.0)
            ),
            "resistance_take_profit_min_pct": _clamp_non_negative(
                _to_float(p.get("resistance_take_profit_min_pct"), 0.0)
            ),
            "profit_time_stop_sec": max(0, int(_to_float(p.get("profit_time_stop_sec"), 0.0))),
            "profit_time_stop_min_pct": _clamp_non_negative(_to_float(p.get("profit_time_stop_min_pct"), 0.0)),
            "profit_time_stop_peak_giveback_pct": _clamp_non_negative(
                _to_float(p.get("profit_time_stop_peak_giveback_pct"), 0.0)
            ),
            "volume_exhaustion_take_profit_min_pct": _clamp_non_negative(
                _to_float(p.get("volume_exhaustion_take_profit_min_pct"), 0.0)
            ),
            "volume_exhaustion_volume_ratio_max": _clamp_non_negative(
                _to_float(p.get("volume_exhaustion_volume_ratio_max"), 0.0)
            ),
            "volume_exhaustion_strength_max": _clamp_non_negative(
                _to_float(p.get("volume_exhaustion_strength_max"), 0.0)
            ),
            "opening_gap_profit_take_min_pct": _clamp_non_negative(
                _to_float(p.get("opening_gap_profit_take_min_pct"), 0.0)
            ),
            "opening_gap_profit_take_window_sec": max(
                0,
                int(_to_float(p.get("opening_gap_profit_take_window_sec"), 0.0)),
            ),
            "opening_gap_profit_take_fraction": _clamp_non_negative(
                _to_float(p.get("opening_gap_profit_take_fraction"), 0.0)
            ),
            "etf_premium_take_profit_enabled": _to_bool(
                p.get("etf_premium_take_profit_enabled"),
                True,
            ),
            "etf_premium_take_profit_pct": _clamp_non_negative(
                _to_float(p.get("etf_premium_take_profit_pct"), DEFAULT_PREMIUM_TRIGGER_PCT)
            ),
            "etf_premium_take_profit_min_pct": _clamp_non_negative(
                _to_float(p.get("etf_premium_take_profit_min_pct"), 0.0)
            ),
            "cost_aware_profit_floor_enabled": _to_bool(p.get("cost_aware_profit_floor_enabled"), False),
            "round_trip_cost_floor_pct": _clamp_non_negative(_to_float(p.get("round_trip_cost_floor_pct"), 0.0)),
            "min_net_profit_buffer_pct": _clamp_non_negative(_to_float(p.get("min_net_profit_buffer_pct"), 0.0)),
            "cost_aware_profit_floor_pct": _clamp_non_negative(
                _to_float(p.get("cost_aware_profit_floor_pct"), 0.0)
            ),
            "cost_aware_profit_floor_use_expected_exit": _to_bool(
                p.get("cost_aware_profit_floor_use_expected_exit"),
                True,
            ),
        "sell_slippage_buffer_pct": _clamp_non_negative(
            _to_float(p.get("sell_slippage_buffer_pct"), 0.0)
        ),
            "min_expected_net_profit_pct": _clamp_non_negative(
                _to_float(
                    p.get("min_expected_net_profit_pct"),
                    _to_float(p.get("min_net_profit_buffer_pct"), 0.0),
                )
            ),
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
            "confirm_required_for_peak_drawdown": max(
                1,
                int(
                    _to_float(
                        p.get("confirm_required_for_peak_drawdown"),
                        2.0,
                    )
                ),
            ),
            "vwap_breakdown_pct": _clamp_non_negative(_to_float(p.get("vwap_breakdown_pct"), 0.0)),
            "vwap_breakdown_confirm_bars": max(
                1,
                int(_to_float(p.get("vwap_breakdown_confirm_bars"), 2.0)),
            ),
            "intraday_low_break_pct": _clamp_non_negative(_to_float(p.get("intraday_low_break_pct"), 0.0)),
            "trend_strength_floor": _to_float(p.get("trend_strength_floor"), 0.0),
            "eod_flat_cutoff_min": max(0, int(_to_float(p.get("eod_flat_cutoff_min"), 10))),
        },
    }
    out["peak_drawdown_mode"] = str(out["thresholds"].get("peak_drawdown_mode") or "profit_protection")
    if bool(out["thresholds"].get("cost_aware_profit_floor_enabled")):
        explicit_floor = float(out["thresholds"].get("cost_aware_profit_floor_pct") or 0.0)
        cost_floor = float(out["thresholds"].get("round_trip_cost_floor_pct") or 0.0)
        buffer = float(out["thresholds"].get("min_net_profit_buffer_pct") or 0.0)
        out["thresholds"]["cost_aware_profit_floor_pct"] = float(max(explicit_floor, cost_floor + buffer))
    else:
        out["thresholds"]["cost_aware_profit_floor_pct"] = 0.0
    out["cost_aware_profit_floor_enabled"] = bool(out["thresholds"].get("cost_aware_profit_floor_enabled"))
    out["cost_aware_profit_floor_pct"] = float(out["thresholds"].get("cost_aware_profit_floor_pct") or 0.0)
    out["cost_aware_profit_floor_met"] = False
    out["cost_aware_profit_floor_gap_pct"] = None
    out["cost_aware_profit_floor_blocked"] = False

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
        if not inferred_metric_name and final_reason in {
            "hard_stop",
            "stop_loss",
            "take_profit",
            "partial_take_profit",
            "profit_ladder",
            "risk_reward_take_profit",
            "opening_gap_profit_take",
            "etf_premium_take_profit",
            "time_decay_profit_exit",
        }:
            inferred_metric_name = "effective_pnl_ratio"
            inferred_metric_value = out.get("effective_pnl_ratio")
            inferred_metric_source = "effective_pnl_ratio"
        elif not inferred_metric_name and final_reason == "volume_exhaustion_take_profit":
            inferred_metric_name = "volume_ratio"
            inferred_metric_value = out.get("volume_ratio")
            inferred_metric_source = "selected.features.volume_ratio"
        elif not inferred_metric_name and final_reason == "vwap_extension_take_profit":
            inferred_metric_name = "vwap_distance"
            inferred_metric_value = out.get("vwap_distance")
            inferred_metric_source = "selected.features.engine_vwap_distance"
        elif not inferred_metric_name and final_reason == "resistance_take_profit":
            inferred_metric_name = "resistance_distance_pct"
            inferred_metric_value = out.get("resistance_distance_pct")
            inferred_metric_source = str(out.get("resistance_price_source") or "policy.resistance_price")
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
        out["exit_trigger_basis"] = {
            "metric_name": inferred_metric_name,
            "metric_value": inferred_metric_value,
            "metric_source": inferred_metric_source,
        }
        out["final_exit_thresholds"] = dict(out.get("thresholds") or {})
        return out

    has_explicit_time_stop = "time_stop_sec" in p

    q = max(0, int(qty or 0))
    if q <= 0:
        return _finalize(reason="no_position")

    def _mark_exit_sizing(*, fraction: float = 1.0, partial: bool = False) -> None:
        frac = max(0.0, min(float(fraction or 0.0), 1.0))
        if frac <= 0.0:
            frac = 1.0
        exit_qty = max(1, int(float(q) * frac))
        exit_qty = min(int(q), int(exit_qty))
        out["exit_qty"] = int(exit_qty)
        out["exit_qty_fraction"] = float(frac)
        out["partial_exit"] = bool(partial and exit_qty < q)

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
    time_limit_reason = "time_stop" if has_explicit_time_stop and time_stop_sec > 0 else "max_hold"
    time_limit_reached = bool(hold_limit > 0 and hs is not None and hs >= hold_limit)
    out["hold_limit_sec"] = int(hold_limit)
    out["max_hold_reached"] = bool(max_hold_sec > 0 and hs is not None and hs >= max_hold_sec)
    out["time_stop_reached"] = bool(time_stop_sec > 0 and hs is not None and hs >= time_stop_sec)
    out["time_limit_reached"] = bool(time_limit_reached)
    out["time_limit_reason"] = time_limit_reason if time_limit_reached else ""
    out["time_limit_reassessment_required"] = bool(time_limit_reached)
    out["time_limit_reassessment_blocked"] = False
    out["time_limit_reassessment_blocked_reason"] = ""

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
    raw_px = _to_float(crosscheck.get("raw_price"), 0.0) if crosscheck.get("raw_price") is not None else 0.0
    technical_px = float(raw_px if raw_px > 0.0 else px)
    out["technical_price"] = float(technical_px) if technical_px > 0.0 else None
    out["technical_price_source"] = "raw_price" if raw_px > 0.0 else str(out.get("effective_price_source") or "")
    if px <= 0.0 or technical_px <= 0.0 or apx <= 0.0:
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
    raw_pnl_ratio = crosscheck.get("raw_pnl_ratio")
    gross_pnl_ratio = (
        float(raw_pnl_ratio)
        if raw_pnl_ratio is not None
        else float((technical_px / apx) - 1.0)
        if technical_px > 0.0 and apx > 0.0
        else pnl_ratio
    )
    out["pnl_ratio"] = pnl_ratio
    out["gross_pnl_ratio"] = gross_pnl_ratio
    out["technical_pnl_ratio"] = gross_pnl_ratio
    out["effective_pnl_ratio"] = pnl_ratio
    out["stop_pnl_ratio"] = gross_pnl_ratio
    out["stop_pnl_ratio_source"] = str(out.get("technical_price_source") or "technical_price")
    out["hard_stop_pnl_ratio"] = pnl_ratio
    out["hard_stop_pnl_ratio_source"] = str(out.get("effective_price_source") or "effective_price")
    if pnl_ratio < gross_pnl_ratio - 1e-9:
        out["cost_drag_pressure"] = True
        out["cost_drag_pressure_pct"] = float(gross_pnl_ratio - pnl_ratio)
        out["cost_drag_pressure_reason"] = str(out.get("pnl_crosscheck_reason") or "effective_pnl_below_gross_pnl")
    profit_floor_pct = float(out["thresholds"].get("cost_aware_profit_floor_pct") or 0.0)
    profit_floor_enabled = bool(out["thresholds"].get("cost_aware_profit_floor_enabled")) and profit_floor_pct > 0.0
    round_trip_cost_floor_pct = float(out["thresholds"].get("round_trip_cost_floor_pct") or 0.0)
    min_expected_net_profit_pct = float(out["thresholds"].get("min_expected_net_profit_pct") or 0.0)
    gross_net_profit_ratio = float(gross_pnl_ratio - round_trip_cost_floor_pct)
    gross_profit_floor_gap_pct = (
        float(
            max(
                profit_floor_pct - gross_pnl_ratio,
                min_expected_net_profit_pct - gross_net_profit_ratio,
                0.0,
            )
        )
        if profit_floor_enabled
        else 0.0
    )
    gross_profit_floor_met = bool(
        (not profit_floor_enabled)
        or (
            gross_pnl_ratio >= profit_floor_pct
            and gross_net_profit_ratio >= min_expected_net_profit_pct
        )
    )
    out["gross_net_profit_ratio"] = float(gross_net_profit_ratio)
    out["gross_profit_floor_met"] = bool(gross_profit_floor_met)
    out["gross_profit_floor_gap_pct"] = float(gross_profit_floor_gap_pct)

    def _first_positive_price(*keys: str) -> tuple[float, str]:
        for key in keys:
            value = p.get(key)
            if value in (None, ""):
                continue
            candidate = _to_float(value, 0.0)
            if candidate > 0.0:
                return float(candidate), key
        return 0.0, ""

    expected_exit_price = 0.0
    expected_exit_source = ""
    expected_exit_fallback_used = False
    expected_exit_slippage_buffer_pct = float(out["thresholds"].get("sell_slippage_buffer_pct") or 0.0)
    # Profit exits are evaluated against executable/raw price context, not
    # account PnL marks that may already include fee/tax drag. Otherwise the
    # round-trip floor is effectively counted twice.
    observed_exit_price = float(technical_px if technical_px > 0.0 else px)
    best_bid, best_bid_source = _first_positive_price(
        "expected_exit_best_bid",
        "best_bid",
        "quote_best_bid",
        "bid",
        "bid_price",
    )
    if best_bid > 0.0:
        expected_exit_price = float(min(best_bid, observed_exit_price))
        expected_exit_source = str(best_bid_source)
    elif expected_exit_slippage_buffer_pct > 0.0 and observed_exit_price > 0.0:
        expected_exit_price = float(observed_exit_price * max(0.0, 1.0 - expected_exit_slippage_buffer_pct))
        expected_exit_source = "observed_price_minus_slippage_buffer"
        expected_exit_fallback_used = True
    elif observed_exit_price > 0.0:
        expected_exit_price = float(observed_exit_price)
        expected_exit_source = "observed_price"

    expected_exit_pnl_ratio = (
        float((expected_exit_price / apx) - 1.0)
        if expected_exit_price > 0.0 and apx > 0.0
        else None
    )
    expected_exit_net_pnl_ratio = (
        float(expected_exit_pnl_ratio - round_trip_cost_floor_pct)
        if expected_exit_pnl_ratio is not None
        else None
    )
    expected_exit_profit_floor_met = bool(not profit_floor_enabled)
    expected_exit_profit_floor_gap_pct = None
    if profit_floor_enabled and expected_exit_pnl_ratio is not None:
        expected_exit_profit_floor_met = bool(
            expected_exit_pnl_ratio >= profit_floor_pct
            and (
                expected_exit_net_pnl_ratio is None
                or expected_exit_net_pnl_ratio >= min_expected_net_profit_pct
            )
        )
        expected_exit_profit_floor_gap_pct = float(
            max(
                profit_floor_pct - expected_exit_pnl_ratio,
                min_expected_net_profit_pct - float(expected_exit_net_pnl_ratio or 0.0),
                0.0,
            )
        )
    floor_source = "expected_exit_pnl_ratio" if expected_exit_pnl_ratio is not None else "gross_pnl_ratio"
    cost_aware_profit_floor_met = (
        bool(expected_exit_profit_floor_met)
        if profit_floor_enabled
        and bool(out["thresholds"].get("cost_aware_profit_floor_use_expected_exit"))
        and expected_exit_pnl_ratio is not None
        else bool(gross_profit_floor_met)
    )
    expected_exit_floor_blocked = bool(
        profit_floor_enabled
        and bool(out["thresholds"].get("cost_aware_profit_floor_use_expected_exit"))
        and gross_profit_floor_met
        and not expected_exit_profit_floor_met
    )
    out["cost_aware_profit_floor_met"] = bool(cost_aware_profit_floor_met)
    out["cost_aware_profit_floor_source"] = str(floor_source if profit_floor_enabled else "disabled")
    if profit_floor_enabled:
        out["cost_aware_profit_floor_gap_pct"] = (
            expected_exit_profit_floor_gap_pct
            if (
                bool(out["thresholds"].get("cost_aware_profit_floor_use_expected_exit"))
                and expected_exit_pnl_ratio is not None
            )
            else gross_profit_floor_gap_pct
        )
    out["expected_exit_price"] = expected_exit_price if expected_exit_price > 0.0 else None
    out["expected_exit_price_source"] = expected_exit_source
    out["expected_exit_price_fallback_used"] = bool(expected_exit_fallback_used)
    out["expected_exit_slippage_buffer_pct"] = float(expected_exit_slippage_buffer_pct)
    out["expected_exit_pnl_ratio"] = expected_exit_pnl_ratio
    out["expected_exit_net_pnl_ratio"] = expected_exit_net_pnl_ratio
    out["expected_exit_profit_floor_met"] = bool(expected_exit_profit_floor_met)
    out["expected_exit_profit_floor_gap_pct"] = expected_exit_profit_floor_gap_pct
    out["expected_exit_profit_floor_blocked"] = bool(expected_exit_floor_blocked)
    if expected_exit_floor_blocked:
        out["expected_exit_profit_floor_blocked_reason"] = "expected_exit_price_below_cost_aware_floor"
    profit_exit_pnl_ratio = (
        float(expected_exit_pnl_ratio)
        if expected_exit_pnl_ratio is not None
        and bool(out["thresholds"].get("cost_aware_profit_floor_use_expected_exit"))
        else float(gross_pnl_ratio)
    )
    profit_exit_metric_name = (
        "expected_exit_pnl_ratio"
        if expected_exit_pnl_ratio is not None
        and bool(out["thresholds"].get("cost_aware_profit_floor_use_expected_exit"))
        else "gross_pnl_ratio"
    )
    out["profit_exit_pnl_ratio"] = float(profit_exit_pnl_ratio)
    out["profit_exit_metric_name"] = str(profit_exit_metric_name)

    def _profit_threshold(base: float) -> float:
        return float(max(float(base or 0.0), profit_floor_pct if profit_floor_enabled else 0.0))

    def _profit_floor_blocks_current_profit() -> bool:
        return bool(
            profit_floor_enabled
            and 0.0 < gross_pnl_ratio
            and (not bool(out.get("cost_aware_profit_floor_met")) or expected_exit_floor_blocked)
        )

    def _mark_profit_floor_blocked() -> None:
        if not _profit_floor_blocks_current_profit():
            return
        out["cost_aware_profit_floor_blocked"] = True
        if not str(out.get("hold_block_reason") or "").strip():
            out["hold_block_reason"] = (
                "expected_exit_profit_floor_not_met"
                if expected_exit_floor_blocked
                else "cost_aware_profit_floor_not_met"
            )

    def _protective_exit_hard_invalidation(reason: str) -> bool:
        r = str(reason or "").strip().lower()
        if _to_bool(p.get("hard_invalidation_confirmed"), False) or _to_bool(
            p.get(f"{r}_hard_invalidation"),
            False,
        ):
            out["protective_exit_hard_invalidation_reason"] = "explicit_policy_flag"
            return True

        structure_signal = str(out.get("structure_breakdown_signal") or "").strip()
        if structure_signal:
            out["protective_exit_hard_invalidation_reason"] = f"chart_structure:{structure_signal}"
            return True

        if r == "vwap_breakdown":
            threshold = float(out["thresholds"].get("vwap_breakdown_pct") or 0.0)
            vwap_distance = _to_float(out.get("vwap_distance"), 0.0)
            hard_multiplier = max(1.0, _to_float(p.get("vwap_breakdown_hard_multiplier"), 2.0))
            hard_extra = max(0.0, _to_float(p.get("vwap_breakdown_hard_extra_pct"), 0.005))
            hard_threshold = max(float(threshold * hard_multiplier), float(threshold + hard_extra))
            if threshold > 0.0 and vwap_distance <= -hard_threshold:
                out["protective_exit_hard_invalidation_reason"] = f"vwap_breakdown_deep:{vwap_distance:.4f}"
                return True

        if r == "intraday_low_break":
            threshold = float(out["thresholds"].get("intraday_low_break_pct") or 0.0)
            prior_bar_low = _to_float(out.get("prior_bar_low"), 0.0)
            hard_multiplier = max(1.0, _to_float(p.get("intraday_low_break_hard_multiplier"), 2.0))
            hard_extra = max(0.0, _to_float(p.get("intraday_low_break_hard_extra_pct"), 0.005))
            hard_threshold = max(float(threshold * hard_multiplier), float(threshold + hard_extra))
            if threshold > 0.0 and prior_bar_low > 0.0 and technical_px <= float(prior_bar_low * (1.0 - hard_threshold)):
                out["protective_exit_hard_invalidation_reason"] = f"intraday_low_break_deep:{hard_threshold:.4f}"
                return True

        return False

    def _block_protective_exit_below_floor(reason: str) -> bool:
        if not _profit_floor_blocks_current_profit():
            return False
        if _protective_exit_hard_invalidation(reason):
            hard_reason = str(out.get("protective_exit_hard_invalidation_reason") or "")
            metric_only_hard_invalidation = hard_reason.startswith(
                ("vwap_breakdown_deep:", "intraday_low_break_deep:")
            )
            out["protective_exit_hard_invalidation"] = True
            if not (metric_only_hard_invalidation and 0.0 < gross_pnl_ratio < profit_floor_pct):
                return False
            out["protective_exit_hard_invalidation_suppressed_by_cost_floor"] = True
            out["protective_exit_hard_invalidation_suppressed_reason"] = hard_reason
        _mark_profit_floor_blocked()
        out["protective_exit_floor_blocked"] = True
        out["protective_exit_floor_blocked_reason"] = str(reason or "")
        out["hold_block_reason"] = f"{str(reason or 'protective_exit')}:cost_aware_profit_floor_not_met"
        return True

    sl = float(out["thresholds"]["stop_loss_pct"])
    hard_sl = float(out["thresholds"]["hard_stop_pct"])
    tp = float(out["thresholds"]["take_profit_pct"])
    etf_deviation_pct = normalize_deviation_pct(p.get("etf_deviation_pct"))
    etf_deviation_source = str(p.get("etf_deviation_source") or "")
    out["etf_deviation_pct"] = etf_deviation_pct
    out["etf_deviation_source"] = etf_deviation_source
    etf_premium_score = score_etf_deviation_for_exit(
        etf_deviation_pct,
        premium_trigger_pct=float(out["thresholds"].get("etf_premium_take_profit_pct") or DEFAULT_PREMIUM_TRIGGER_PCT),
    )
    out["etf_premium_take_profit_score"] = float(etf_premium_score)

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

    hard_stop_pnl_ratio = float(out["hard_stop_pnl_ratio"])
    stop_pnl_ratio = float(out["stop_pnl_ratio"])
    if hard_sl > 0.0 and hard_stop_pnl_ratio <= -hard_sl:
        return _finalize(
            triggered=True,
            reason="hard_stop",
            metric_name="hard_stop_pnl_ratio",
            metric_value=hard_stop_pnl_ratio,
            metric_source=str(out.get("hard_stop_pnl_ratio_source") or "effective_pnl_ratio"),
        )
    if sl > 0.0 and stop_pnl_ratio <= -sl:
        return _finalize(
            triggered=True,
            reason="stop_loss",
            metric_name="stop_pnl_ratio",
            metric_value=stop_pnl_ratio,
            metric_source=str(out.get("stop_pnl_ratio_source") or "technical_pnl_ratio"),
        )
    if sl > 0.0 and pnl_ratio <= -sl and stop_pnl_ratio > -sl:
        out["stop_loss_cost_drag_blocked"] = True
        out["stop_loss_cost_drag_blocked_reason"] = "net_pnl_stop_loss_without_technical_stop"
        if not str(out.get("hold_block_reason") or "").strip():
            out["hold_block_reason"] = "stop_loss_cost_drag_only"

    etf_premium_take_profit_enabled = bool(out["thresholds"].get("etf_premium_take_profit_enabled"))
    etf_premium_take_profit_pct = float(out["thresholds"].get("etf_premium_take_profit_pct") or 0.0)
    etf_premium_take_profit_min_pct = float(out["thresholds"].get("etf_premium_take_profit_min_pct") or 0.0)
    etf_premium_take_profit_armed = bool(
        etf_premium_take_profit_enabled
        and etf_deviation_pct is not None
        and etf_premium_take_profit_pct > 0.0
        and float(etf_deviation_pct) >= etf_premium_take_profit_pct
    )
    out["etf_premium_take_profit_armed"] = bool(etf_premium_take_profit_armed)
    if etf_premium_take_profit_armed:
        min_profit = _profit_threshold(etf_premium_take_profit_min_pct)
        if profit_exit_pnl_ratio >= min_profit and not _profit_floor_blocks_current_profit():
            return _finalize(
                triggered=True,
                reason="etf_premium_take_profit",
                metric_name="etf_deviation_pct",
                metric_value=etf_deviation_pct,
                metric_source=etf_deviation_source or "selected.features.etf_deviation_pct",
            )
        if _profit_floor_blocks_current_profit():
            _mark_profit_floor_blocked()
            out["hold_block_reason"] = "etf_premium_take_profit:cost_aware_profit_floor_not_met"

    if tp > 0.0 and profit_exit_pnl_ratio >= _profit_threshold(tp) and not _profit_floor_blocks_current_profit():
        return _finalize(triggered=True, reason="take_profit")

    peak_price = _to_float(p.get("peak_price"), 0.0)
    if peak_price <= 0.0:
        peak_price = max(apx, technical_px)
    if peak_price > 0.0:
        max_runup_pct = float((peak_price / apx) - 1.0) if apx > 0.0 else 0.0
        peak_drawdown = float((technical_px / peak_price) - 1.0)
        peak_drawdown_mode = str(out["thresholds"].get("peak_drawdown_mode") or "profit_protection").strip().lower()
        if not peak_drawdown_mode:
            peak_drawdown_mode = "profit_protection"
        activation_pct = _profit_threshold(float(out["thresholds"].get("profit_protection_activation_pct") or 0.0))
        peak_profit_floor_required_pct = float(activation_pct)
        peak_profit_floor_met = bool(max_runup_pct >= peak_profit_floor_required_pct)
        peak_drawdown_block_reason = ""
        if peak_drawdown_mode in {"disabled", "off", "none"}:
            peak_drawdown_armed = False
        elif peak_drawdown_mode in {"profit_protection", "profit-protection"}:
            peak_drawdown_armed = bool(peak_profit_floor_met)
            if not peak_drawdown_armed:
                peak_drawdown_block_reason = "profit_floor_not_reached"
        else:
            peak_drawdown_armed = True
            peak_profit_floor_met = True
        out["max_runup_pct"] = max_runup_pct
        out["peak_drawdown"] = peak_drawdown
        out["peak_drawdown_from_peak"] = peak_drawdown
        out["peak_drawdown_armed"] = bool(peak_drawdown_armed)
        out["peak_drawdown_mode"] = str(peak_drawdown_mode)
        out["peak_drawdown_blocked"] = bool(not peak_drawdown_armed and bool(peak_drawdown_block_reason))
        out["peak_drawdown_block_reason"] = str(peak_drawdown_block_reason)
        out["peak_drawdown_profit_floor_required_pct"] = float(peak_profit_floor_required_pct)
        out["peak_drawdown_profit_floor_met"] = bool(peak_profit_floor_met)
        out["final_peak_drawdown_ratio"] = peak_drawdown
        out["peak_drawdown_source"] = f"{str(out.get('technical_price_source') or 'technical_price')}_vs_peak_price"

        peak_drawdown_th = float(out["thresholds"]["peak_drawdown_exit_pct"])
        profit_protection_urgent = bool(
            peak_drawdown_th > 0.0
            and peak_drawdown_armed
            and peak_drawdown <= -peak_drawdown_th
            and profit_floor_enabled
            and profit_floor_pct > 0.0
            and peak_profit_floor_met
            and gross_pnl_ratio < profit_floor_pct
        )
        out["peak_drawdown_profit_protection_urgent"] = bool(profit_protection_urgent)
        if profit_protection_urgent:
            out["peak_drawdown_profit_protection_reason"] = "max_runup_crossed_cost_floor_then_gave_back"
        if (
            peak_drawdown_th > 0.0
            and peak_drawdown_armed
            and peak_drawdown <= -peak_drawdown_th
            and (profit_protection_urgent or not _profit_floor_blocks_current_profit())
        ):
            return _finalize(
                triggered=True,
                reason="peak_drawdown",
                metric_name="peak_drawdown_ratio",
                metric_value=peak_drawdown,
                metric_source=str(out.get("peak_drawdown_source") or "technical_price_vs_peak_price"),
            )

    vwap_breakdown_th = float(out["thresholds"]["vwap_breakdown_pct"])
    if vwap_breakdown_th > 0.0:
        vwap_distance = _to_float(p.get("vwap_distance"), 0.0)
        out["vwap_distance"] = float(vwap_distance)
        vwap_distance_source = str(p.get("vwap_distance_source") or "selected.features.engine_vwap_distance")
        require_profit = _to_bool(p.get("vwap_break_requires_profit"), True)
        if vwap_distance <= -vwap_breakdown_th and (not require_profit or peak_price > apx or gross_pnl_ratio > 0.0):
            confirmation_required = _to_bool(p.get("vwap_breakdown_confirmation_required"), True)
            confirm_bars_required = int(out["thresholds"].get("vwap_breakdown_confirm_bars") or 2)
            consecutive_bars = max(0, int(_to_float(p.get("vwap_breakdown_consecutive_bars"), 0.0)))
            low_break_confirmed = _to_bool(p.get("vwap_breakdown_low_break_confirmed"), False)
            volume_confirmed = _to_bool(p.get("vwap_breakdown_volume_confirmed"), False)
            confirmed = bool(
                not confirmation_required
                or consecutive_bars >= confirm_bars_required
                or low_break_confirmed
                or volume_confirmed
                or _to_bool(p.get("hard_invalidation_confirmed"), False)
                or _to_bool(p.get("vwap_breakdown_hard_invalidation"), False)
            )
            out["vwap_breakdown_confirmation_required"] = bool(confirmation_required)
            out["vwap_breakdown_consecutive_bars"] = int(consecutive_bars)
            out["vwap_breakdown_confirm_bars_required"] = int(confirm_bars_required)
            out["vwap_breakdown_low_break_confirmed"] = bool(low_break_confirmed)
            out["vwap_breakdown_volume_confirmed"] = bool(volume_confirmed)
            out["vwap_breakdown_confirmed"] = bool(confirmed)
            if not confirmed:
                out["vwap_breakdown_confirmation_pending"] = True
                out["vwap_breakdown_confirmation_reason"] = (
                    f"need_{confirm_bars_required}_bars_or_volume_or_low_break"
                )
                if not str(out.get("hold_block_reason") or "").strip():
                    out["hold_block_reason"] = "vwap_breakdown_confirmation_pending"
            elif _block_protective_exit_below_floor("vwap_breakdown"):
                pass
            else:
                return _finalize(
                    triggered=True,
                    reason="vwap_breakdown",
                    metric_name="vwap_distance",
                    metric_value=vwap_distance,
                    metric_source=vwap_distance_source,
                )

    intraday_low_break_pct = float(out["thresholds"]["intraday_low_break_pct"])
    if intraday_low_break_pct > 0.0:
        prior_bar_low = _to_float(p.get("prior_bar_low"), 0.0)
        out["prior_bar_low"] = float(prior_bar_low)
        if prior_bar_low > 0.0 and technical_px <= float(prior_bar_low * (1.0 - intraday_low_break_pct)):
            if _block_protective_exit_below_floor("intraday_low_break"):
                pass
            else:
                return _finalize(triggered=True, reason="intraday_low_break")

    trend_strength_floor = float(out["thresholds"]["trend_strength_floor"])
    if trend_strength_floor != 0.0:
        trend_strength = _to_float(p.get("trend_strength"), 0.0)
        out["trend_strength"] = float(trend_strength)
        vwap_distance = _to_float(p.get("vwap_distance"), out.get("vwap_distance") or 0.0)
        out["vwap_distance"] = float(vwap_distance)
        if trend_strength <= trend_strength_floor and vwap_distance < 0.0:
            return _finalize(triggered=True, reason="trend_breakdown")

    opening_gap_min_pct = float(out["thresholds"]["opening_gap_profit_take_min_pct"])
    opening_gap_min_pct = _profit_threshold(opening_gap_min_pct)
    opening_gap_window_sec = int(out["thresholds"]["opening_gap_profit_take_window_sec"])
    if opening_gap_min_pct > 0.0 and profit_exit_pnl_ratio >= opening_gap_min_pct and not _profit_floor_blocks_current_profit():
        opening_gap_observed = _to_bool(p.get("opening_gap_chase_observed"), False)
        open_gap_pct = _to_float(p.get("open_gap_pct"), 0.0)
        prev_close_distance_pct = _to_float(p.get("prev_close_distance_pct"), 0.0)
        out["opening_gap_chase_observed"] = bool(opening_gap_observed)
        out["open_gap_pct"] = float(open_gap_pct)
        out["prev_close_distance_pct"] = float(prev_close_distance_pct)
        if opening_gap_observed and (opening_gap_window_sec <= 0 or hs is None or hs <= opening_gap_window_sec):
            _mark_exit_sizing(
                fraction=float(out["thresholds"]["opening_gap_profit_take_fraction"] or 1.0),
                partial=False,
            )
            return _finalize(
                triggered=True,
                reason="opening_gap_profit_take",
                metric_name=profit_exit_metric_name,
                metric_value=profit_exit_pnl_ratio,
                metric_source=profit_exit_metric_name,
            )

    volume_exhaustion_min_pct = float(out["thresholds"]["volume_exhaustion_take_profit_min_pct"])
    volume_exhaustion_min_pct = _profit_threshold(volume_exhaustion_min_pct)
    if (
        volume_exhaustion_min_pct > 0.0
        and profit_exit_pnl_ratio >= volume_exhaustion_min_pct
        and not _profit_floor_blocks_current_profit()
    ):
        volume_ratio = _to_float(p.get("volume_ratio"), 0.0)
        execution_strength = _to_float(p.get("execution_strength"), 0.0)
        trade_strength = _to_float(p.get("trade_strength"), 0.0)
        volume_ratio_max = float(out["thresholds"]["volume_exhaustion_volume_ratio_max"])
        strength_max = float(out["thresholds"]["volume_exhaustion_strength_max"])
        out["volume_ratio"] = float(volume_ratio)
        out["execution_strength"] = float(execution_strength)
        out["trade_strength"] = float(trade_strength)
        volume_exhausted = bool(volume_ratio_max > 0.0 and 0.0 < volume_ratio <= volume_ratio_max)
        strength_exhausted = bool(
            strength_max > 0.0
            and (
                (execution_strength > 0.0 and execution_strength <= strength_max)
                or (trade_strength > 0.0 and trade_strength <= strength_max)
            )
        )
        if volume_exhausted or strength_exhausted:
            return _finalize(
                triggered=True,
                reason="volume_exhaustion_take_profit",
                metric_name="volume_ratio" if volume_exhausted else "execution_strength",
                metric_value=volume_ratio if volume_exhausted else execution_strength or trade_strength,
                metric_source="selected.features.volume_ratio" if volume_exhausted else "selected.features.execution_strength",
            )

    partial_take_profit_pct = float(out["thresholds"]["partial_take_profit_pct"])
    partial_take_profit_effective_pct = _profit_threshold(partial_take_profit_pct)
    partial_take_profit_taken = _to_bool(p.get("partial_take_profit_taken"), False)
    out["partial_take_profit_taken"] = bool(partial_take_profit_taken)
    if (
        partial_take_profit_pct > 0.0
        and not partial_take_profit_taken
        and profit_exit_pnl_ratio >= partial_take_profit_effective_pct
        and not _profit_floor_blocks_current_profit()
    ):
        _mark_exit_sizing(
            fraction=float(out["thresholds"]["partial_take_profit_fraction"] or 0.5),
            partial=True,
        )
        return _finalize(
            triggered=True,
            reason="partial_take_profit",
            metric_name=profit_exit_metric_name,
            metric_value=profit_exit_pnl_ratio,
            metric_source=profit_exit_metric_name,
        )

    profit_ladder_levels = list(out["thresholds"].get("profit_ladder_levels_pct") or [])
    profit_ladder_taken = set(round(x, 6) for x in _to_float_list(p.get("profit_ladder_taken_levels")))
    if profit_ladder_levels:
        ladder_candidates = [
            float(level)
            for level in profit_ladder_levels
            if float(level) >= _profit_threshold(0.0)
            and profit_exit_pnl_ratio >= float(level)
            and round(float(level), 6) not in profit_ladder_taken
            and not (partial_take_profit_pct > 0.0 and float(level) <= partial_take_profit_pct)
        ]
        if ladder_candidates and not _profit_floor_blocks_current_profit():
            selected_ladder = max(ladder_candidates)
            out["profit_ladder_level_pct"] = float(selected_ladder)
            out["profit_ladder_level_index"] = int(profit_ladder_levels.index(selected_ladder))
            ladder_fraction = float(out["thresholds"]["profit_ladder_fraction"] or 0.34)
            if selected_ladder >= max(profit_ladder_levels):
                ladder_fraction = 1.0
            _mark_exit_sizing(fraction=ladder_fraction, partial=ladder_fraction < 1.0)
            return _finalize(
                triggered=True,
                reason="profit_ladder",
                metric_name=profit_exit_metric_name,
                metric_value=profit_exit_pnl_ratio,
                metric_source=profit_exit_metric_name,
            )

    rr_take_profit_rungs = list(out["thresholds"].get("risk_reward_take_profit_rungs") or [])
    rr_single = float(out["thresholds"]["risk_reward_take_profit_r"])
    if not rr_take_profit_rungs and rr_single > 0.0:
        rr_take_profit_rungs = [rr_single]
    rr_taken = set(round(x, 6) for x in _to_float_list(p.get("risk_reward_take_profit_taken_rungs")))
    if rr_take_profit_rungs and effective_stop_pct > 0.0:
        rr_candidates = [
            float(rung)
            for rung in rr_take_profit_rungs
            if profit_exit_pnl_ratio >= _profit_threshold(
                max(float(effective_stop_pct * float(rung)), float(out["thresholds"]["risk_reward_take_profit_min_pct"]))
            )
            and round(float(rung), 6) not in rr_taken
        ]
        if rr_candidates and not _profit_floor_blocks_current_profit():
            selected_rung = max(rr_candidates)
            rr_target_pct = max(
                float(effective_stop_pct * selected_rung),
                float(out["thresholds"]["risk_reward_take_profit_min_pct"]),
                _profit_threshold(0.0),
            )
            out["risk_reward_take_profit_rung"] = float(selected_rung)
            out["risk_reward_take_profit_target_pct"] = float(rr_target_pct)
            rr_fraction = float(out["thresholds"]["risk_reward_take_profit_fraction"] or 0.34)
            if selected_rung >= max(rr_take_profit_rungs):
                rr_fraction = 1.0
            _mark_exit_sizing(fraction=rr_fraction, partial=rr_fraction < 1.0)
            return _finalize(
                triggered=True,
                reason="risk_reward_take_profit",
                metric_name=profit_exit_metric_name,
                metric_value=profit_exit_pnl_ratio,
                metric_source=profit_exit_metric_name,
            )

    if peak_price > 0.0:
        resistance_near_pct = float(out["thresholds"]["resistance_take_profit_near_pct"])
        resistance_min_pct = _profit_threshold(float(out["thresholds"]["resistance_take_profit_min_pct"]))
        if (
            resistance_near_pct > 0.0
            and profit_exit_pnl_ratio >= resistance_min_pct
            and not _profit_floor_blocks_current_profit()
        ):
            resistance_candidates: list[tuple[str, float]] = []
            for resistance_key in (
                "resistance_price",
                "target_resistance_price",
                "upper_resistance_price",
                "day_high",
                "intraday_high",
                "recent_high",
                "breakout_level",
                "prior_bar_high",
            ):
                resistance_value = _to_float(p.get(resistance_key), 0.0)
                if resistance_value > 0.0 and resistance_value >= technical_px:
                    resistance_candidates.append((resistance_key, resistance_value))
            if resistance_candidates:
                resistance_source, resistance_price = min(resistance_candidates, key=lambda row: float(row[1]))
                resistance_distance = float((resistance_price / technical_px) - 1.0)
                out["resistance_price"] = float(resistance_price)
                out["resistance_price_source"] = f"policy.{resistance_source}"
                out["resistance_distance_pct"] = float(resistance_distance)
                if 0.0 <= resistance_distance <= resistance_near_pct:
                    return _finalize(
                        triggered=True,
                        reason="resistance_take_profit",
                        metric_name="resistance_distance_pct",
                        metric_value=resistance_distance,
                        metric_source=f"policy.{resistance_source}",
                    )

        vwap_extension_th = float(out["thresholds"]["vwap_extension_take_profit_pct"])
        vwap_extension_min_pct = _profit_threshold(float(out["thresholds"]["vwap_extension_take_profit_min_pct"]))
        if (
            vwap_extension_th > 0.0
            and profit_exit_pnl_ratio >= vwap_extension_min_pct
            and not _profit_floor_blocks_current_profit()
        ):
            vwap_distance = _to_float(p.get("vwap_distance"), 0.0)
            out["vwap_distance"] = float(vwap_distance)
            if vwap_distance >= vwap_extension_th:
                return _finalize(
                    triggered=True,
                    reason="vwap_extension_take_profit",
                    metric_name="vwap_distance",
                    metric_value=vwap_distance,
                    metric_source="selected.features.engine_vwap_distance",
                )

        profit_time_stop_sec = int(out["thresholds"]["profit_time_stop_sec"])
        profit_time_stop_min_pct = _profit_threshold(float(out["thresholds"]["profit_time_stop_min_pct"]))
        profit_time_stop_giveback_pct = float(out["thresholds"]["profit_time_stop_peak_giveback_pct"])
        out["profit_time_stop_peak_giveback_pct"] = float(profit_time_stop_giveback_pct)
        if (
            profit_time_stop_sec > 0
            and hs is not None
            and hs >= profit_time_stop_sec
            and profit_exit_pnl_ratio >= profit_time_stop_min_pct
            and (profit_time_stop_giveback_pct <= 0.0 or peak_drawdown <= -profit_time_stop_giveback_pct)
            and not _profit_floor_blocks_current_profit()
        ):
            return _finalize(
                triggered=True,
                reason="time_decay_profit_exit",
                metric_name=profit_exit_metric_name,
                metric_value=profit_exit_pnl_ratio,
                metric_source=profit_exit_metric_name,
            )

    # Trailing stop (optional).
    trail = float(out["thresholds"]["trailing_stop_pct"])
    if trail > 0.0:
        if peak_price > 0.0:
            drawdown = float((technical_px / peak_price) - 1.0)
            out["trailing_drawdown"] = drawdown
            if drawdown <= -trail and not _profit_floor_blocks_current_profit():
                return _finalize(triggered=True, reason="trailing_stop")

    if time_limit_reached:
        if not profit_floor_enabled:
            return _finalize(
                triggered=True,
                reason=time_limit_reason,
                metric_name="hold_sec",
                metric_value=hs,
                metric_source="position_age_seconds",
            )
        if bool(out.get("cost_aware_profit_floor_met")) and not expected_exit_floor_blocked:
            return _finalize(
                triggered=True,
                reason=time_limit_reason,
                metric_name="hold_sec",
                metric_value=hs,
                metric_source="position_age_seconds",
            )

        out["time_limit_reassessment_blocked"] = True
        if gross_pnl_ratio > 0.0:
            _mark_profit_floor_blocked()
            blocked_reason = (
                "expected_exit_profit_floor_not_met"
                if expected_exit_floor_blocked
                else "cost_aware_profit_floor_not_met"
            )
            out["time_limit_reassessment_blocked_reason"] = f"{time_limit_reason}:{blocked_reason}"
            out["hold_block_reason"] = f"{time_limit_reason}:{blocked_reason}"
        else:
            out["time_limit_reassessment_blocked_reason"] = (
                f"{time_limit_reason}:time_limit_reached_without_profit_floor"
            )
            if not str(out.get("hold_block_reason") or "").strip():
                out["hold_block_reason"] = f"{time_limit_reason}:time_limit_reached_without_profit_floor"

    _mark_profit_floor_blocked()
    if out["price_anomaly_flag"] and not out["hold_block_reason"]:
        out["hold_block_reason"] = f"price_anomaly_fallback:{str(out.get('price_anomaly_reason') or '')}".strip(":")
    return _finalize(reason="hold")
