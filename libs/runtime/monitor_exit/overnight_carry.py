from __future__ import annotations

from collections.abc import Callable
from typing import Any, Dict

from libs.core.symbols import normalize_symbol
from libs.runtime.exit_policy import apply_account_pnl_crosscheck_context, evaluate_exit_policy
from libs.runtime.monitor_exit.position_tracking import position_hold_seconds
from libs.runtime.monitor_exit.preview import preview_exit_decision_for_symbol
from libs.runtime.monitor_exit.reasons import is_soft_profit_exit_reason
from libs.runtime.monitor_exit.runtime_clock import carry_calendar_context


def _is_trueish(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


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


def persist_overnight_decision(
    state: Dict[str, Any],
    *,
    symbol: str,
    decision: Dict[str, Any] | None = None,
    clear: bool = False,
) -> None:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    rows = (
        persisted.get("overnight_decision_by_symbol")
        if isinstance(persisted.get("overnight_decision_by_symbol"), dict)
        else {}
    )
    key = normalize_symbol(symbol)
    if not key:
        return
    if clear:
        rows.pop(key, None)
    elif isinstance(decision, dict) and decision:
        rows[key] = dict(decision)
    if rows:
        persisted["overnight_decision_by_symbol"] = rows
    else:
        persisted.pop("overnight_decision_by_symbol", None)
    state["persisted_state"] = persisted


def evaluate_overnight_carry_decision(
    *,
    state: Dict[str, Any],
    symbol: str,
    position: Dict[str, Any],
    selected: Dict[str, Any] | None,
    exit_policy_base: Dict[str, Any],
    primary_decision: Dict[str, Any],
    frame: Dict[str, Any],
    hold_sec: int,
) -> Dict[str, Any]:
    thresholds = primary_decision.get("thresholds") if isinstance(primary_decision.get("thresholds"), dict) else {}
    minutes_to_close = _optional_float(primary_decision.get("minutes_to_close"))
    if minutes_to_close is None:
        minutes_to_close = _optional_float(exit_policy_base.get("minutes_to_close"))
    cutoff_min = int(_to_float(thresholds.get("eod_flat_cutoff_min") or exit_policy_base.get("eod_flat_cutoff_min") or 10))
    use_eod_flat = bool(exit_policy_base.get("use_eod_flat"))
    qty = max(0, _to_int(position.get("qty")))
    calendar_context = carry_calendar_context(state)
    weekend_carry = bool(calendar_context.get("weekend_carry"))
    allow_weekend_carry = (
        _is_trueish(exit_policy_base.get("allow_weekend_carry"))
        or _is_trueish(frame.get("allow_weekend_carry"))
        or _is_trueish(state.get("allow_weekend_carry"))
    )
    out: Dict[str, Any] = {
        "evaluated": False,
        "approved": False,
        "action": "not_applicable",
        "reason": "",
        "anomaly": False,
        "anomaly_reason": "",
        "minutes_to_close": minutes_to_close,
        "cutoff_min": int(cutoff_min),
        "positive_signals": [],
        "blockers": [],
        "non_eod_reason": "",
        "non_eod_triggered": False,
        "pnl_ratio": None,
        "trend_strength": None,
        "vwap_distance": None,
        "peak_drawdown": None,
        "playbook": str(frame.get("playbook") or ""),
        "monitor_guidance": str(frame.get("monitor_guidance") or ""),
        "risk_tone": str(frame.get("risk_tone") or ""),
        "carry_calendar": dict(calendar_context),
        "weekend_carry": bool(weekend_carry),
        "allow_weekend_carry": bool(allow_weekend_carry),
        "holding_gap_days": int(calendar_context.get("holding_gap_days") or 1),
    }
    if qty <= 0 or (not use_eod_flat) or minutes_to_close is None or minutes_to_close < 0.0 or minutes_to_close > float(cutoff_min):
        if qty > 0 and bool(use_eod_flat) and minutes_to_close is None:
            out["anomaly"] = True
            out["anomaly_reason"] = "minutes_to_close_missing"
        return out

    out["evaluated"] = True
    out["action"] = "flatten_before_close"

    no_eod_policy = dict(exit_policy_base or {})
    no_eod_policy["use_eod_flat"] = False
    no_eod_policy["minutes_to_close"] = float(minutes_to_close)
    no_eod_policy = apply_account_pnl_crosscheck_context(no_eod_policy, position=position)
    risk_decision = evaluate_exit_policy(
        price=primary_decision.get("_price"),
        avg_price=primary_decision.get("_avg_price"),
        qty=qty,
        hold_sec=hold_sec if hold_sec > 0 else None,
        policy=no_eod_policy,
    )
    out["non_eod_reason"] = str(risk_decision.get("reason") or "")
    out["non_eod_triggered"] = bool(risk_decision.get("triggered"))

    pnl_ratio = _optional_float(risk_decision.get("pnl_ratio"))
    trend_strength = _optional_float(((selected or {}).get("features") or {}).get("engine_trend_strength"))
    vwap_distance = _optional_float(((selected or {}).get("features") or {}).get("engine_vwap_distance"))
    peak_drawdown = _optional_float(risk_decision.get("peak_drawdown"))
    out["pnl_ratio"] = pnl_ratio
    out["trend_strength"] = trend_strength
    out["vwap_distance"] = vwap_distance
    out["peak_drawdown"] = peak_drawdown

    blockers: list[str] = []
    positives: list[str] = []
    if bool(risk_decision.get("triggered")):
        risk_reason = str(risk_decision.get("reason") or "unknown")
        if is_soft_profit_exit_reason(risk_reason):
            positives.append(f"soft_profit_exit_available:{risk_reason}")
            out["non_eod_triggered"] = False
        else:
            blockers.append(f"underlying_exit_signal:{risk_reason}")
    if str(frame.get("monitor_guidance") or "").strip().lower() == "defensive_exit":
        blockers.append("monitor_guidance:defensive_exit")
    if str(frame.get("playbook") or "").strip().lower() == "defensive":
        blockers.append("playbook:defensive")
    if str(frame.get("risk_tone") or "").strip().lower() == "conservative":
        blockers.append("risk_tone:conservative")

    if pnl_ratio is None:
        blockers.append("pnl:unavailable")
    elif pnl_ratio < -0.003:
        blockers.append(f"pnl_below_carry_floor:{pnl_ratio:.4f}")
    else:
        positives.append(f"pnl_ok:{pnl_ratio:.4f}")

    if trend_strength is not None:
        if trend_strength < 0.05:
            blockers.append(f"trend_strength_weak:{trend_strength:.4f}")
        else:
            positives.append(f"trend_strength_ok:{trend_strength:.4f}")

    if vwap_distance is not None:
        if vwap_distance < -0.003:
            blockers.append(f"vwap_below_floor:{vwap_distance:.4f}")
        else:
            positives.append(f"vwap_ok:{vwap_distance:.4f}")

    if peak_drawdown is not None:
        if peak_drawdown < -0.012:
            blockers.append(f"peak_drawdown_too_deep:{peak_drawdown:.4f}")
        else:
            positives.append(f"peak_drawdown_ok:{peak_drawdown:.4f}")

    if weekend_carry:
        _apply_weekend_carry_checks(
            blockers=blockers,
            positives=positives,
            allow_weekend_carry=allow_weekend_carry,
            exit_policy_base=exit_policy_base,
            frame=frame,
            pnl_ratio=pnl_ratio,
            trend_strength=trend_strength,
            vwap_distance=vwap_distance,
        )

    playbook = str(frame.get("playbook") or "").strip().lower()
    if playbook in ("breakout", "pullback"):
        positives.append(f"playbook:{playbook}")
    guidance = str(frame.get("monitor_guidance") or "").strip().lower()
    if guidance in ("hold_through_noise", "trend_follow"):
        positives.append(f"monitor_guidance:{guidance}")

    out["positive_signals"] = list(positives)
    out["blockers"] = list(blockers)
    if not blockers and len(positives) >= 2:
        out["approved"] = True
        out["action"] = "carry_overnight"
        out["reason"] = "carry_overnight_approved"
    else:
        out["approved"] = False
        out["action"] = "flatten_before_close"
        out["reason"] = str(blockers[0] if blockers else "carry_conditions_not_met")
    return out


def _apply_weekend_carry_checks(
    *,
    blockers: list[str],
    positives: list[str],
    allow_weekend_carry: bool,
    exit_policy_base: Dict[str, Any],
    frame: Dict[str, Any],
    pnl_ratio: float | None,
    trend_strength: float | None,
    vwap_distance: float | None,
) -> None:
    if not allow_weekend_carry:
        blockers.append("weekend_carry_not_allowed:friday")
        return
    weekend_pnl_floor = _optional_float(exit_policy_base.get("weekend_carry_min_pnl_ratio"))
    if weekend_pnl_floor is None:
        weekend_pnl_floor = _optional_float(frame.get("weekend_carry_min_pnl_ratio"))
    if weekend_pnl_floor is None:
        weekend_pnl_floor = 0.005
    weekend_trend_floor = _optional_float(exit_policy_base.get("weekend_carry_min_trend_strength"))
    if weekend_trend_floor is None:
        weekend_trend_floor = _optional_float(frame.get("weekend_carry_min_trend_strength"))
    if weekend_trend_floor is None:
        weekend_trend_floor = 0.15
    if pnl_ratio is None or pnl_ratio < float(weekend_pnl_floor):
        blockers.append(f"weekend_pnl_buffer_insufficient:{(pnl_ratio if pnl_ratio is not None else 0.0):.4f}")
    else:
        positives.append(f"weekend_pnl_buffer_ok:{pnl_ratio:.4f}")
    if trend_strength is None or trend_strength < float(weekend_trend_floor):
        blockers.append(f"weekend_trend_buffer_insufficient:{(trend_strength if trend_strength is not None else 0.0):.4f}")
    else:
        positives.append(f"weekend_trend_buffer_ok:{trend_strength:.4f}")
    if vwap_distance is None or vwap_distance < 0.0:
        blockers.append(f"weekend_vwap_buffer_insufficient:{(vwap_distance if vwap_distance is not None else 0.0):.4f}")
    else:
        positives.append(f"weekend_vwap_buffer_ok:{vwap_distance:.4f}")


def persist_eod_carry_decisions_for_open_positions(
    *,
    state: Dict[str, Any],
    pos_map: Dict[str, Dict[str, Any]],
    selected: Dict[str, Any] | None,
    exit_policy_base: Dict[str, Any],
    frame: Dict[str, Any],
    now_epoch: int,
    preview_resolver: Callable[..., Dict[str, Any]] | None = None,
    hold_seconds_resolver: Callable[[Dict[str, Any], str, Dict[str, Any]], int] | None = None,
) -> Dict[str, Any]:
    rows: list[Dict[str, Any]] = []
    selected_symbol = normalize_symbol((selected or {}).get("symbol")) if isinstance(selected, dict) else ""
    preview = preview_resolver or preview_exit_decision_for_symbol
    hold_resolver = hold_seconds_resolver or position_hold_seconds
    for sym, pos in sorted(pos_map.items()):
        symbol = normalize_symbol(sym)
        if not symbol or max(0, _to_int((pos or {}).get("qty"))) <= 0:
            continue
        selected_for_symbol = selected if selected_symbol == symbol else {"symbol": symbol}
        decision = preview(
            state=state,
            symbol=symbol,
            position=pos,
            selected=selected_for_symbol,
            exit_policy_base=exit_policy_base,
        )
        hold_sec = _to_int(decision.get("_hold_sec"))
        if hold_sec <= 0:
            hold_sec = hold_resolver(state, symbol, pos)
        eod_carry = evaluate_overnight_carry_decision(
            state=state,
            symbol=symbol,
            position=pos,
            selected=selected_for_symbol,
            exit_policy_base=exit_policy_base,
            primary_decision=decision,
            frame=frame,
            hold_sec=hold_sec,
        )
        if not bool(eod_carry.get("evaluated")):
            continue
        payload = eod_carry_payload(symbol=symbol, eod_carry=eod_carry, now_epoch=now_epoch)
        persist_overnight_decision(state, symbol=symbol, decision=payload)
        rows.append(payload)
    return {
        "evaluated_count": len(rows),
        "symbols": [str(row.get("symbol") or "") for row in rows],
        "decisions": rows,
    }


def eod_carry_payload(*, symbol: str, eod_carry: Dict[str, Any], now_epoch: int) -> Dict[str, Any]:
    return {
        "approved": bool(eod_carry.get("approved")),
        "action": str(eod_carry.get("action") or ""),
        "reason": str(eod_carry.get("reason") or ""),
        "minutes_to_close": eod_carry.get("minutes_to_close"),
        "cutoff_min": eod_carry.get("cutoff_min"),
        "positive_signals": list(eod_carry.get("positive_signals") or []),
        "blockers": list(eod_carry.get("blockers") or []),
        "carry_calendar": dict(eod_carry.get("carry_calendar") or {}),
        "weekend_carry": bool(eod_carry.get("weekend_carry")),
        "allow_weekend_carry": bool(eod_carry.get("allow_weekend_carry")),
        "holding_gap_days": eod_carry.get("holding_gap_days"),
        "decided_at_epoch": int(now_epoch),
        "symbol": str(symbol or ""),
    }
