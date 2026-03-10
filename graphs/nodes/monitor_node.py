from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

from graphs.nodes.skill_contracts import (
    CONTRACT_VERSION as SKILL_CONTRACT_VERSION,
    extract_market_quotes,
    extract_order_status,
)
from libs.runtime.exit_policy import evaluate_exit_policy
from libs.runtime.position_sizing import evaluate_position_size


def _to_int(v: Any) -> int:
    try:
        return int(float(v))
    except Exception:
        return 0


def _normalize_status(v: Any) -> str:
    return str(v or "").strip().upper()


def _to_float(v: Any) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def _is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _resolve_min_hold_sec(state: Dict[str, Any], policy: Dict[str, Any]) -> int:
    raw = policy.get("min_hold_seconds") if isinstance(policy, dict) else None
    if raw is None:
        raw = os.getenv("MIN_HOLD_SECONDS", "600")
    try:
        return max(0, int(float(raw)))
    except Exception:
        return 600


def _resolve_sell_cooldown_sec(state: Dict[str, Any], policy: Dict[str, Any]) -> int:
    raw = policy.get("sell_cooldown_sec") if isinstance(policy, dict) else None
    if raw is None:
        raw = os.getenv("SELL_COOLDOWN", "")
    if raw in (None, ""):
        raw = os.getenv("SELL_COOLDOWN_SEC", "300")
    try:
        return max(0, int(float(raw)))
    except Exception:
        return 300


def _resolve_exit_confirm_ticks(state: Dict[str, Any], policy: Dict[str, Any]) -> int:
    raw = policy.get("exit_confirm_ticks") if isinstance(policy, dict) else None
    if raw is None:
        raw = os.getenv("MONITOR_EXIT_CONFIRM_TICKS", "2")
    try:
        return max(1, int(float(raw)))
    except Exception:
        return 2


def _norm_symbol(v: Any) -> str:
    return str(v or "").strip().upper()


def _make_event_logger(state: Dict[str, Any]) -> Any:
    injected = state.get("event_logger")
    if injected is not None and hasattr(injected, "log"):
        return injected
    from libs.core.event_logger import EventLogger

    log_path = os.getenv("EVENT_LOG_PATH", "./data/logs/events.jsonl")
    return EventLogger(log_path=Path(log_path))


def _log_monitor_summary(state: Dict[str, Any], payload: Dict[str, Any]) -> None:
    try:
        logger = _make_event_logger(state)
        run_id = str(state.get("run_id") or "monitor-node")
        logger.log(run_id=run_id, stage="monitor", event="summary", payload=dict(payload))
    except Exception:
        return


def _resolve_cash(state: Dict[str, Any]) -> float:
    snapshot = state.get("portfolio_snapshot")
    if isinstance(snapshot, dict):
        c = _to_float(snapshot.get("cash"))
        if c > 0.0:
            return c
    snaps = state.get("snapshots")
    if isinstance(snaps, dict):
        port = snaps.get("portfolio")
        if isinstance(port, dict):
            c = _to_float(port.get("cash"))
            if c > 0.0:
                return c
    return 0.0


def _portfolio_exposure(state: Dict[str, Any], price_fallback: float = 0.0) -> float:
    cash = _resolve_cash(state)
    pos_map = _position_by_symbol(state)
    invested = 0.0
    for row in pos_map.values():
        qty = max(0, _to_int(row.get("qty")))
        if qty <= 0:
            continue
        px = _to_float(row.get("price"))
        if px <= 0.0:
            px = _to_float(row.get("avg_price"))
        if px <= 0.0:
            px = price_fallback
        if px <= 0.0:
            continue
        invested += float(qty) * float(px)
    denom = cash + invested
    if denom <= 0.0:
        return 0.0
    return float(invested / denom)


def _build_sizing_risk_context(state: Dict[str, Any], selected: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    rc = dict(state.get("risk_context") or {}) if isinstance(state.get("risk_context"), dict) else {}
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    features = selected.get("features") if isinstance(selected.get("features"), dict) else {}
    regime = str(features.get("engine_regime") or selected.get("regime") or policy.get("regime") or "").strip().lower()
    vol20 = _to_float(features.get("engine_volatility20"))
    vol_pct = _to_float(policy.get("volatility_percentile"))
    if vol_pct <= 0.0 and vol20 > 0.0:
        vol_pct = min(max(vol20 / 0.05, 0.0), 1.0)

    price = _resolve_price(state, symbol, selected) or 0.0
    exposure = _portfolio_exposure(state, price_fallback=float(price))
    corr_bucket = str(policy.get("correlation_bucket") or "medium").strip().lower()
    daily_pnl_ratio = _to_float(rc.get("daily_pnl_ratio"))
    daily_loss_limit = abs(_to_float(policy.get("risk_daily_loss_limit")))
    if daily_loss_limit <= 0.0:
        daily_loss_limit = 0.02
    daily_loss_state = daily_pnl_ratio <= -daily_loss_limit if daily_loss_limit > 0 else False
    degrade_mode = bool(state.get("degrade_mode"))
    rs = state.get("resilience_state") if isinstance(state.get("resilience_state"), dict) else {}
    if str(rs.get("mode") or "").strip().lower() == "degrade":
        degrade_mode = True

    rc.update(
        {
            "regime": regime or None,
            "volatility_percentile": float(vol_pct),
            "portfolio_exposure": float(exposure),
            "correlation_bucket": corr_bucket,
            "daily_loss_state": bool(daily_loss_state),
            "degrade_mode": bool(degrade_mode),
        }
    )
    return rc


def _position_by_symbol(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    snapshot = state.get("portfolio_snapshot")
    if isinstance(snapshot, dict) and isinstance(snapshot.get("positions"), list):
        for row in snapshot.get("positions") or []:
            if not isinstance(row, dict):
                continue
            sym = _norm_symbol(row.get("symbol") or row.get("stk_cd") or row.get("code"))
            if not sym:
                continue
            out[sym] = dict(row)
        return out

    snaps = state.get("snapshots")
    if isinstance(snaps, dict):
        port = snaps.get("portfolio")
        if isinstance(port, dict) and isinstance(port.get("positions"), list):
            for row in port.get("positions") or []:
                if not isinstance(row, dict):
                    continue
                sym = _norm_symbol(row.get("symbol") or row.get("stk_cd") or row.get("code"))
                if not sym:
                    continue
                out[sym] = dict(row)
    return out


def _resolve_price(state: Dict[str, Any], symbol: str, selected: Dict[str, Any] | None) -> float | None:
    sym = _norm_symbol(symbol)
    if not sym:
        return None

    if isinstance(selected, dict):
        direct = selected.get("price")
        if direct is not None:
            p = _to_float(direct)
            if p > 0.0:
                return p
        features = selected.get("features")
        if isinstance(features, dict):
            x = features.get("skill_quote_price")
            if x is not None:
                p = _to_float(x)
                if p > 0.0:
                    return p

    mkt = state.get("market_snapshot")
    if isinstance(mkt, dict):
        ms = _norm_symbol(mkt.get("symbol"))
        px = mkt.get("price")
        if ms == sym and px is not None:
            p = _to_float(px)
            if p > 0.0:
                return p

    quotes, _meta = extract_market_quotes(state)
    q = quotes.get(sym)
    if isinstance(q, dict):
        for k in ("price", "cur"):
            if q.get(k) is not None:
                p = _to_float(q.get(k))
                if p > 0.0:
                    return p
    return None


def _derive_order_lifecycle(order_status: Dict[str, Any] | None) -> Dict[str, Any] | None:
    if not isinstance(order_status, dict):
        return None

    status = _normalize_status(order_status.get("status"))
    filled_qty = max(0, _to_int(order_status.get("filled_qty")))
    order_qty = max(0, _to_int(order_status.get("order_qty")))

    if order_qty > 0:
        progress = min(1.0, float(filled_qty) / float(order_qty))
    else:
        progress = 0.0

    cancelled_keys = ("CANCEL", "CANCELED", "CANCELLED")
    rejected_keys = ("REJECT", "DENY", "BLOCK")
    filled_keys = ("FILLED", "DONE")
    partial_keys = ("PARTIAL", "WORKING_PARTIAL")

    stage = "working"
    terminal = False

    if any(k in status for k in cancelled_keys):
        stage = "cancelled"
        terminal = True
    elif any(k in status for k in rejected_keys):
        stage = "rejected"
        terminal = True
    elif (order_qty > 0 and filled_qty >= order_qty) or any(k in status for k in filled_keys):
        stage = "filled"
        terminal = True
        progress = 1.0
    elif (filled_qty > 0 and order_qty > 0 and filled_qty < order_qty) or any(k in status for k in partial_keys):
        stage = "partial_fill"
        terminal = False
    elif not status:
        stage = "unknown"
        terminal = False

    return {
        "ord_no": order_status.get("ord_no"),
        "symbol": order_status.get("symbol"),
        "status_raw": order_status.get("status"),
        "stage": stage,
        "terminal": terminal,
        "filled_qty": filled_qty,
        "order_qty": order_qty,
        "progress": float(progress),
    }


def monitor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """Graph node: Monitor.

    Responsibility:
      - emit at most one intent from selected candidate
      - attach optional order status/lifecycle observation from skill DTOs
    """
    selected = state.get("selected")
    plan = state.get("plan") or {}

    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}

    intents = []
    sizing_info: Dict[str, Any] = {
        "enabled": False,
        "evaluated": False,
        "qty": 1,
        "reason": "disabled",
        "price": None,
        "cash": None,
        "inputs": {},
    }
    if isinstance(selected, dict) and selected.get("symbol"):
        symbol = str(selected.get("symbol"))
        qty = 1
        use_position_sizing = _is_trueish(state.get("use_position_sizing")) or _is_trueish(policy.get("use_position_sizing"))
        if use_position_sizing:
            px = _resolve_price(state, symbol, selected)
            cash = _resolve_cash(state)
            sizing_risk_context = _build_sizing_risk_context(state, selected, symbol)
            sz = evaluate_position_size(
                price=px,
                cash=cash if cash > 0.0 else None,
                policy=policy.get("position_sizing") if isinstance(policy.get("position_sizing"), dict) else policy,
                risk_context=sizing_risk_context,
            )
            qty = max(0, _to_int(sz.get("qty")))
            sizing_info = {
                "enabled": True,
                "evaluated": bool(sz.get("evaluated")),
                "qty": int(qty),
                "reason": str(sz.get("reason") or ""),
                "price": sz.get("price"),
                "cash": sz.get("cash"),
                "inputs": sz.get("inputs") if isinstance(sz.get("inputs"), dict) else {},
            }
        else:
            sizing_info = {
                "enabled": False,
                "evaluated": False,
                "qty": 1,
                "reason": "disabled",
                "price": None,
                "cash": None,
                "inputs": {},
            }

        if qty <= 0:
            intents = []
        else:
            intent = {
                "symbol": symbol,
                "side": "BUY",
                "qty": int(qty),
                "thesis": str(plan.get("thesis") or ""),
                "meta": {
                    "score": selected.get("score"),
                    "risk_score": selected.get("risk_score"),
                    "confidence": selected.get("confidence"),
                },
            }
            if bool(sizing_info.get("enabled")):
                intent["meta"]["sizing"] = {
                    "reason": str(sizing_info.get("reason") or ""),
                    "price": sizing_info.get("price"),
                    "cash": sizing_info.get("cash"),
                    "inputs": sizing_info.get("inputs"),
                }
            intents = [intent]

    # Optional M29-2 exit policy (default disabled for backward compatibility).
    use_exit_policy = _is_trueish(state.get("use_exit_policy")) or _is_trueish(policy.get("use_exit_policy"))
    exit_info: Dict[str, Any] = {
        "enabled": bool(use_exit_policy),
        "evaluated": False,
        "triggered": False,
        "reason": "",
        "symbol": None,
        "qty": 0,
        "pnl_ratio": None,
        "price": None,
        "avg_price": None,
    }
    if use_exit_policy and isinstance(selected, dict) and selected.get("symbol"):
        symbol = _norm_symbol(selected.get("symbol"))
        pos_map = _position_by_symbol(state)
        pos = pos_map.get(symbol, {})
        qty = max(0, _to_int(pos.get("qty")))
        # When a position is already held for selected symbol, suppress fresh BUY intents.
        if qty > 0:
            intents = []
        avg_price = _to_float(pos.get("avg_price"))
        price = _resolve_price(state, symbol, selected)
        features = selected.get("features") if isinstance(selected.get("features"), dict) else {}
        hold_sec = _to_int(pos.get("hold_sec"))
        if hold_sec <= 0:
            hold_sec = _to_int(state.get("position_hold_sec"))
        exit_policy = policy.get("exit_policy") if isinstance(policy.get("exit_policy"), dict) else policy
        exit_policy_map = dict(exit_policy or {})
        if pos.get("peak_price") is not None:
            exit_policy_map.setdefault("peak_price", pos.get("peak_price"))
        elif pos.get("high_water_mark") is not None:
            exit_policy_map.setdefault("peak_price", pos.get("high_water_mark"))
        if features.get("engine_volatility20") is not None:
            exit_policy_map.setdefault("current_volatility", features.get("engine_volatility20"))
        if policy.get("exit_policy_baseline_volatility") is not None:
            exit_policy_map.setdefault("baseline_volatility", policy.get("exit_policy_baseline_volatility"))
        if state.get("emergency_halt") is not None:
            exit_policy_map.setdefault("emergency_halt", state.get("emergency_halt"))
        mctx = state.get("market_context") if isinstance(state.get("market_context"), dict) else {}
        if mctx.get("minutes_to_close") is not None:
            exit_policy_map.setdefault("minutes_to_close", mctx.get("minutes_to_close"))
        decision = evaluate_exit_policy(
            price=price,
            avg_price=avg_price if avg_price > 0.0 else None,
            qty=qty,
            hold_sec=hold_sec if hold_sec > 0 else None,
            policy=exit_policy_map,
        )
        min_hold_sec = max(
            _resolve_min_hold_sec(state, policy),
            _resolve_sell_cooldown_sec(state, policy),
        )
        confirm_ticks = _resolve_exit_confirm_ticks(state, policy)
        confirm_map = state.get("_monitor_exit_confirm")
        if not isinstance(confirm_map, dict):
            confirm_map = {}
        confirm_key = f"{symbol}:{str(decision.get('reason') or '').strip()}"
        confirm_count = 0
        sell_guard_blocked = False
        sell_guard_reason = ""

        if bool(decision.get("triggered")):
            if min_hold_sec > 0 and hold_sec > 0 and hold_sec < min_hold_sec:
                sell_guard_blocked = True
                sell_guard_reason = f"sell_guard_min_hold:{hold_sec}s<{min_hold_sec}s"
            elif int(features.get("skill_open_orders") or 0) > 0:
                sell_guard_blocked = True
                sell_guard_reason = "sell_guard_open_order_pending"
            elif confirm_ticks > 1:
                confirm_count = _to_int(confirm_map.get(confirm_key)) + 1
                confirm_map[confirm_key] = int(confirm_count)
                if confirm_count < int(confirm_ticks):
                    sell_guard_blocked = True
                    sell_guard_reason = f"exit_confirmation_pending:{confirm_count}/{confirm_ticks}"
        else:
            if confirm_key in confirm_map:
                confirm_map.pop(confirm_key, None)

        if not sell_guard_blocked and bool(decision.get("triggered")) and confirm_key in confirm_map:
            confirm_map.pop(confirm_key, None)
        state["_monitor_exit_confirm"] = confirm_map

        exit_info = {
            "enabled": True,
            "evaluated": bool(decision.get("evaluated")),
            "triggered": bool(decision.get("triggered")) and not bool(sell_guard_blocked),
            "reason": (
                str(sell_guard_reason)
                if str(sell_guard_reason).strip()
                else str(decision.get("reason") or "")
            ),
            "symbol": symbol,
            "qty": int(qty),
            "pnl_ratio": decision.get("pnl_ratio"),
            "price": price,
            "avg_price": avg_price if avg_price > 0.0 else None,
            "thresholds": decision.get("thresholds") if isinstance(decision.get("thresholds"), dict) else {},
            "hold_sec": hold_sec if hold_sec > 0 else None,
            "trailing_drawdown": decision.get("trailing_drawdown"),
            "volatility_ratio": decision.get("volatility_ratio"),
            "minutes_to_close": decision.get("minutes_to_close"),
            "min_hold_sec": int(min_hold_sec),
            "exit_confirm_ticks": int(confirm_ticks),
            "exit_confirm_count": int(confirm_count),
            "sell_guard_blocked": bool(sell_guard_blocked),
            "sell_guard_reason": str(sell_guard_reason),
        }
        if bool(decision.get("triggered")) and not bool(sell_guard_blocked) and qty > 0:
            intents = [
                {
                    "symbol": symbol,
                    "side": "SELL",
                    "qty": int(qty),
                    "thesis": str(plan.get("thesis") or ""),
                    "meta": {
                        "exit_reason": str(decision.get("reason") or ""),
                        "pnl_ratio": decision.get("pnl_ratio"),
                        "avg_price": avg_price if avg_price > 0.0 else None,
                        "price": price,
                        "source": "monitor_exit_policy",
                        "reason": str(decision.get("reason") or ""),
                        "signal_source": "monitor_exit_policy",
                        "position_age_sec": hold_sec if hold_sec > 0 else None,
                    },
                }
            ]

    order_status, order_status_meta = extract_order_status(state)
    order_lifecycle = _derive_order_lifecycle(order_status)
    fallback_reasons = list(order_status_meta.get("errors") or [])

    state["intents"] = intents
    state["monitor"] = {
        "skill_contract_version": SKILL_CONTRACT_VERSION,
        "has_intent": bool(intents),
        "intent_count": len(intents),
        "selected_symbol": (selected.get("symbol") if isinstance(selected, dict) else None),
        "order_status_loaded": bool(order_status),
        "order_status": order_status,
        "order_status_present": bool(order_status_meta.get("present")),
        "order_status_fallback": bool(fallback_reasons),
        "order_status_fallback_reasons": fallback_reasons,
        "order_status_error_count": len(fallback_reasons),
        "order_lifecycle_loaded": bool(order_lifecycle),
        "order_lifecycle": order_lifecycle,
        "exit_policy_enabled": bool(exit_info.get("enabled")),
        "exit_evaluated": bool(exit_info.get("evaluated")),
        "exit_triggered": bool(exit_info.get("triggered")),
        "exit_reason": str(exit_info.get("reason") or ""),
        "exit_pnl_ratio": exit_info.get("pnl_ratio"),
        "exit_symbol": exit_info.get("symbol"),
        "exit_qty": int(exit_info.get("qty") or 0),
        "position_sizing_enabled": bool(sizing_info.get("enabled")),
        "position_sizing_evaluated": bool(sizing_info.get("evaluated")),
        "position_sizing_qty": int(sizing_info.get("qty") or 0),
        "position_sizing_reason": str(sizing_info.get("reason") or ""),
    }
    state["monitor_output"] = {
        "selected_symbol": (selected.get("symbol") if isinstance(selected, dict) else None),
        "intent_side": (str(intents[0].get("side")) if intents else "NOOP"),
        "intent_qty": (int(intents[0].get("qty") or 0) if intents else 0),
        "entry_exit_reason": (
            str(exit_info.get("reason") or "")
            if bool(exit_info.get("enabled"))
            else "entry_candidate_selected"
        ),
    }
    state["monitor_exit"] = exit_info
    state["monitor_sizing"] = sizing_info
    _log_monitor_summary(
        state,
        {
            "has_intent": bool(intents),
            "intent_count": len(intents),
            "selected_symbol": (selected.get("symbol") if isinstance(selected, dict) else None),
            "order_status_fallback": bool(fallback_reasons),
            "exit_policy_enabled": bool(exit_info.get("enabled")),
            "exit_evaluated": bool(exit_info.get("evaluated")),
            "exit_triggered": bool(exit_info.get("triggered")),
            "exit_reason": str(exit_info.get("reason") or ""),
            "position_sizing_enabled": bool(sizing_info.get("enabled")),
            "position_sizing_evaluated": bool(sizing_info.get("evaluated")),
            "position_sizing_qty": int(sizing_info.get("qty") or 0),
            "position_sizing_reason": str(sizing_info.get("reason") or ""),
        },
    )
    return state
