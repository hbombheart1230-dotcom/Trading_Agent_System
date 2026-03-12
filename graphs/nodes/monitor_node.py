from __future__ import annotations

"""Canonical Monitor node for integrated runtime.

Role boundary:
- monitors selected stock / active position state
- emits entry/exit intents only
- never re-ranks symbol universe and never executes orders
"""

import os
import time
from pathlib import Path
from typing import Any, Dict

from graphs.nodes.skill_contracts import (
    CONTRACT_VERSION as SKILL_CONTRACT_VERSION,
    extract_market_quotes,
    extract_order_status,
)
from libs.research.evidence_ledger import record_decision_bridge, record_raw_input
from libs.runtime.decision_trace import append_decision_trace
from libs.runtime.exit_policy import evaluate_exit_policy
from libs.runtime.position_sizing import evaluate_position_size
from libs.strategies.contracts import coerce_strategist_output


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
    if raw is None and isinstance(policy, dict):
        raw = policy.get("sell_cooldown_seconds")
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


def _resolve_use_exit_policy(state: Dict[str, Any], policy: Dict[str, Any]) -> bool:
    if state.get("use_exit_policy") is not None:
        return _is_trueish(state.get("use_exit_policy"))
    if isinstance(policy, dict) and policy.get("use_exit_policy") is not None:
        return _is_trueish(policy.get("use_exit_policy"))
    return _is_trueish(os.getenv("USE_EXIT_POLICY", "false"))


def _resolve_block_buy_when_open_position(
    state: Dict[str, Any],
    policy: Dict[str, Any],
    monitor_policy: Dict[str, Any],
) -> bool:
    if state.get("monitor_block_buy_when_open_position") is not None:
        return _is_trueish(state.get("monitor_block_buy_when_open_position"))
    if isinstance(monitor_policy, dict) and monitor_policy.get("block_buy_when_open_position") is not None:
        return _is_trueish(monitor_policy.get("block_buy_when_open_position"))
    if isinstance(policy, dict) and policy.get("block_buy_when_open_position") is not None:
        return _is_trueish(policy.get("block_buy_when_open_position"))
    return _is_trueish(os.getenv("MONITOR_BLOCK_BUY_WHEN_OPEN_POSITION", "false"))


def _resolve_exit_policy_config(policy: Dict[str, Any]) -> Dict[str, Any]:
    cfg = policy.get("exit_policy") if isinstance(policy.get("exit_policy"), dict) else {}
    out = dict(cfg or {})

    # Backward-compatible flat policy aliases.
    alias_map = {
        "stop_loss_pct": "stop_loss_pct",
        "take_profit_pct": "take_profit_pct",
        "max_hold_sec": "max_hold_sec",
        "trailing_stop_pct": "trailing_stop_pct",
        "vol_expansion_ratio": "vol_expansion_ratio",
        "news_shock_threshold": "news_shock_threshold",
        "use_eod_flat": "use_eod_flat",
        "eod_flat_cutoff_min": "eod_flat_cutoff_min",
        "emergency_halt": "emergency_halt",
    }
    for src_key, dst_key in alias_map.items():
        if out.get(dst_key) in (None, "") and policy.get(src_key) not in (None, ""):
            out[dst_key] = policy.get(src_key)

    sl_raw = str(os.getenv("EXIT_POLICY_STOP_LOSS_PCT", "") or "").strip()
    tp_raw = str(os.getenv("EXIT_POLICY_TAKE_PROFIT_PCT", "") or "").strip()
    mh_raw = str(os.getenv("EXIT_POLICY_MAX_HOLD_SEC", "") or "").strip()
    trail_raw = str(os.getenv("EXIT_POLICY_TRAILING_STOP_PCT", "") or "").strip()
    vol_exp_raw = str(os.getenv("EXIT_POLICY_VOL_EXPANSION_RATIO", "") or "").strip()
    news_shock_raw = str(os.getenv("EXIT_POLICY_NEWS_SHOCK_THRESHOLD", "") or "").strip()
    eod_flat_raw = str(os.getenv("EXIT_POLICY_USE_EOD_FLAT", "") or "").strip()
    eod_cutoff_raw = str(os.getenv("EXIT_POLICY_EOD_FLAT_CUTOFF_MIN", "") or "").strip()
    emergency_raw = str(os.getenv("EXIT_POLICY_EMERGENCY_HALT", "") or "").strip()

    if sl_raw:
        base = _to_float(out.get("stop_loss_pct"))
        if base <= 0.0:
            base = 0.03
        x = _to_float(sl_raw)
        out["stop_loss_pct"] = float(x if x > 0.0 else base)
    if tp_raw:
        base = _to_float(out.get("take_profit_pct"))
        if base <= 0.0:
            base = 0.05
        x = _to_float(tp_raw)
        out["take_profit_pct"] = float(x if x > 0.0 else base)
    if mh_raw:
        base = _to_float(out.get("max_hold_sec"))
        x = _to_float(mh_raw)
        out["max_hold_sec"] = int(x if x > 0.0 else base)
    if trail_raw:
        base = _to_float(out.get("trailing_stop_pct"))
        x = _to_float(trail_raw)
        out["trailing_stop_pct"] = float(x if x > 0.0 else base)
    if vol_exp_raw:
        base = _to_float(out.get("vol_expansion_ratio"))
        x = _to_float(vol_exp_raw)
        out["vol_expansion_ratio"] = float(x if x > 0.0 else base)
    if news_shock_raw:
        base = _to_float(out.get("news_shock_threshold"))
        x = _to_float(news_shock_raw)
        out["news_shock_threshold"] = float(x if x > 0.0 else base)
    if eod_flat_raw:
        out["use_eod_flat"] = _is_trueish(eod_flat_raw)
    if eod_cutoff_raw:
        base = _to_float(out.get("eod_flat_cutoff_min"))
        if base <= 0.0:
            base = 10.0
        x = _to_float(eod_cutoff_raw)
        out["eod_flat_cutoff_min"] = int(x if x > 0.0 else base)
    if emergency_raw:
        out["emergency_halt"] = _is_trueish(emergency_raw)
    return out


def _extract_monitor_strategy_frame(state: Dict[str, Any]) -> Dict[str, str]:
    strategist_output_raw = state.get("strategist_output")
    strategist_output = (
        coerce_strategist_output(strategist_output_raw)
        if isinstance(strategist_output_raw, dict)
        else {}
    )
    return {
        "playbook": str(
            state.get("playbook")
            or strategist_output.get("playbook")
            or ""
        ).strip().lower(),
        "monitor_guidance": str(
            state.get("monitor_guidance")
            or strategist_output.get("monitor_guidance")
            or ""
        ).strip().lower(),
        "risk_tone": str(
            state.get("risk_tone")
            or strategist_output.get("risk_tone")
            or ""
        ).strip().lower(),
        "trade_aggressiveness": str(
            state.get("trade_aggressiveness")
            or strategist_output.get("trade_aggressiveness")
            or ""
        ).strip().lower(),
    }


def _apply_monitor_strategy_frame(
    *,
    min_hold_sec: int,
    sell_cooldown_sec: int,
    confirm_ticks: int,
    frame: Dict[str, str],
) -> Dict[str, Any]:
    min_hold = max(0, int(min_hold_sec))
    cooldown = max(0, int(sell_cooldown_sec))
    confirm = max(1, int(confirm_ticks))
    adjustments: list[str] = []

    playbook = str(frame.get("playbook") or "").strip().lower()
    mode = str(frame.get("monitor_guidance") or "").strip().lower()
    if not mode:
        if playbook == "breakout":
            mode = "hold_through_noise"
            adjustments.append("playbook:breakout->monitor_guidance")
        elif playbook == "defensive":
            mode = "defensive_exit"
            adjustments.append("playbook:defensive->monitor_guidance")
        elif playbook in ("pullback", "reversal"):
            mode = "quick_take_profit"
            adjustments.append(f"playbook:{playbook}->monitor_guidance")

    if mode == "hold_through_noise":
        min_hold += 300
        confirm += 1
        cooldown += 60
        adjustments.append("monitor_guidance:hold_through_noise")
    elif mode == "defensive_exit":
        min_hold = max(0, min_hold - 120)
        confirm = max(1, confirm - 1)
        adjustments.append("monitor_guidance:defensive_exit")
    elif mode == "quick_take_profit":
        min_hold = max(0, min_hold - 300)
        confirm = 1
        cooldown = max(60, min(cooldown, 180))
        adjustments.append("monitor_guidance:quick_take_profit")

    tone = str(frame.get("risk_tone") or "").strip().lower()
    if tone == "conservative":
        min_hold += 120
        confirm += 1
        adjustments.append("risk_tone:conservative")
    elif tone == "aggressive":
        min_hold = max(0, min_hold - 60)
        confirm = max(1, confirm - 1)
        adjustments.append("risk_tone:aggressive")

    aggr = str(frame.get("trade_aggressiveness") or "").strip().lower()
    if aggr == "low":
        confirm = max(confirm, 3)
        adjustments.append("trade_aggressiveness:low")
    elif aggr == "high":
        confirm = max(1, confirm - 1)
        adjustments.append("trade_aggressiveness:high")

    return {
        "min_hold_sec": max(0, int(min_hold)),
        "sell_cooldown_sec": max(0, int(cooldown)),
        "confirm_ticks": max(1, min(6, int(confirm))),
        "playbook": playbook,
        "monitor_guidance": mode,
        "risk_tone": tone,
        "trade_aggressiveness": aggr,
        "adjustments": list(adjustments),
    }


def _resolve_now_epoch(state: Dict[str, Any]) -> int:
    tick_ts = state.get("tick_ts")
    try:
        if tick_ts is not None:
            return int(float(tick_ts))
    except Exception:
        pass
    return int(time.time())


def _norm_symbol(v: Any) -> str:
    return str(v or "").strip().upper()


def _clear_symbol_confirm_keys(confirm_map: Dict[str, Any], symbol: str) -> None:
    prefix = f"{_norm_symbol(symbol)}:"
    for key in list(confirm_map.keys()):
        if str(key).startswith(prefix):
            confirm_map.pop(key, None)


def _is_emergency_exit_reason(reason: str) -> bool:
    r = str(reason or "").strip().lower()
    return r in ("emergency_halt", "news_shock")


def _is_hard_exit_reason(reason: str) -> bool:
    r = str(reason or "").strip().lower()
    return r in (
        "emergency_halt",
        "news_shock",
        "eod_flat",
        "time_stop",
        "max_hold",
        "stop_loss",
        "volatility_expansion",
        "trailing_stop",
    )


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
    strategist_output = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
    monitor_policy = state.get("monitor_policy") if isinstance(state.get("monitor_policy"), dict) else {}
    if isinstance(strategist_output.get("monitor_policy"), dict):
        monitor_policy = {**dict(strategist_output.get("monitor_policy") or {}), **monitor_policy}
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


def _preview_exit_decision_for_symbol(
    *,
    state: Dict[str, Any],
    symbol: str,
    position: Dict[str, Any],
    selected: Dict[str, Any] | None,
    exit_policy_base: Dict[str, Any],
) -> Dict[str, Any]:
    qty = max(0, _to_int(position.get("qty")))
    avg_price = _to_float(position.get("avg_price"))
    selected_for_exit = selected if isinstance(selected, dict) else {"symbol": symbol}
    price = _resolve_price(state, symbol, selected_for_exit)
    if price is None or _to_float(price) <= 0.0:
        pos_mark = _position_mark_price(position)
        if pos_mark is not None and pos_mark > 0.0:
            price = float(pos_mark)

    features = selected_for_exit.get("features") if isinstance(selected_for_exit.get("features"), dict) else {}
    hold_sec = _to_int(position.get("hold_sec"))
    if hold_sec <= 0:
        hold_sec = _to_int(state.get("position_hold_sec"))
    if hold_sec <= 0:
        persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
        last_trade_side = str(persisted.get("last_trade_side") or "").strip().upper()
        last_trade_epoch = _to_int(persisted.get("last_trade_epoch"))
        if last_trade_side == "BUY" and last_trade_epoch > 0:
            now_epoch = _resolve_now_epoch(state)
            hold_sec = max(0, int(now_epoch - last_trade_epoch))

    exit_policy_map = dict(exit_policy_base or {})
    if position.get("peak_price") is not None:
        exit_policy_map.setdefault("peak_price", position.get("peak_price"))
    elif position.get("high_water_mark") is not None:
        exit_policy_map.setdefault("peak_price", position.get("high_water_mark"))
    if features.get("engine_volatility20") is not None:
        exit_policy_map.setdefault("current_volatility", features.get("engine_volatility20"))
    if state.get("policy") and isinstance(state.get("policy"), dict):
        policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
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
    decision["_qty"] = int(qty)
    decision["_price"] = float(price) if price is not None and _to_float(price) > 0.0 else None
    decision["_avg_price"] = float(avg_price) if avg_price > 0.0 else None
    decision["_hold_sec"] = int(hold_sec) if hold_sec > 0 else None
    decision["_pnl_ratio"] = _to_float(decision.get("pnl_ratio"))
    return decision


def _exit_reason_priority(reason: str) -> int:
    r = str(reason or "").strip().lower()
    order = {
        "emergency_halt": 100,
        "news_shock": 95,
        "eod_flat": 90,
        "time_stop": 80,
        "max_hold": 75,
        "stop_loss": 70,
        "volatility_expansion": 65,
        "trailing_stop": 60,
        "take_profit": 50,
        "hold": 10,
        "price_unavailable": 5,
        "no_position": 0,
    }
    return int(order.get(r, 1))


def _select_exit_symbol(
    selected_symbol: str,
    pos_map: Dict[str, Dict[str, Any]],
    *,
    state: Dict[str, Any] | None = None,
    selected: Dict[str, Any] | None = None,
    policy: Dict[str, Any] | None = None,
    exit_policy_base: Dict[str, Any] | None = None,
) -> str:
    sel = _norm_symbol(selected_symbol)
    if sel and max(0, _to_int((pos_map.get(sel) or {}).get("qty"))) > 0:
        return sel

    held_symbols = [
        _norm_symbol(sym)
        for sym, row in pos_map.items()
        if max(0, _to_int((row or {}).get("qty"))) > 0
    ]
    held_symbols = [s for s in held_symbols if s]
    if not held_symbols:
        return sel

    if state is None:
        # Backward-compatible fallback.
        best_symbol = ""
        best_qty = 0
        for sym, row in pos_map.items():
            qty = max(0, _to_int((row or {}).get("qty")))
            if qty > best_qty:
                best_qty = qty
                best_symbol = _norm_symbol(sym)
        return best_symbol or sel

    base = exit_policy_base if isinstance(exit_policy_base, dict) else {}
    selected_raw = selected if isinstance(selected, dict) else {}
    selected_raw_symbol = _norm_symbol(selected_raw.get("symbol"))
    best_symbol = held_symbols[0]
    best_rank = (-1, -1, -1.0, -1)
    for sym in held_symbols:
        pos = dict(pos_map.get(sym) or {})
        selected_for_exit = selected_raw if selected_raw_symbol == sym else {"symbol": sym}
        decision = _preview_exit_decision_for_symbol(
            state=state,
            symbol=sym,
            position=pos,
            selected=selected_for_exit,
            exit_policy_base=base,
        )
        triggered = 1 if bool(decision.get("triggered")) else 0
        reason_priority = _exit_reason_priority(str(decision.get("reason") or ""))
        pnl_mag = abs(_to_float(decision.get("_pnl_ratio")))
        qty = max(0, _to_int(decision.get("_qty")))
        rank = (triggered, reason_priority, pnl_mag, qty)
        if rank > best_rank:
            best_rank = rank
            best_symbol = sym
    if best_symbol:
        return best_symbol
    return sel


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


def _position_mark_price(position: Dict[str, Any] | None) -> float | None:
    if not isinstance(position, dict):
        return None
    for key in ("price", "cur_price", "last_price", "current_price"):
        p = _to_float(position.get(key))
        if p > 0.0:
            return p
    qty = max(0, _to_int(position.get("qty")))
    avg_price = _to_float(position.get("avg_price"))
    unrealized = _to_float(position.get("unrealized_pnl"))
    if qty > 0 and avg_price > 0.0:
        mark = avg_price + (unrealized / float(qty))
        if mark > 0.0:
            return mark
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
      - keep stock-selection and execution out of monitor scope
    """
    run_id = str(state.get("run_id") or "").strip() or "monitor-unknown"
    selected = state.get("selected")
    plan = state.get("plan") or {}

    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    strategist_output = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
    monitor_policy: Dict[str, Any] = {}
    if isinstance(policy.get("monitor_policy"), dict):
        monitor_policy.update(dict(policy.get("monitor_policy") or {}))
    if isinstance(strategist_output.get("monitor_policy"), dict):
        monitor_policy.update(dict(strategist_output.get("monitor_policy") or {}))
    if isinstance(state.get("monitor_policy"), dict):
        monitor_policy.update(dict(state.get("monitor_policy") or {}))

    all_pos_map = _position_by_symbol(state)
    open_position_count = sum(1 for row in all_pos_map.values() if max(0, _to_int((row or {}).get("qty"))) > 0)
    block_buy_open_position = _resolve_block_buy_when_open_position(state, policy, monitor_policy)
    buy_blocked_open_position = False
    try:
        record_raw_input(
            run_id=run_id,
            agent="monitor",
            stage="entry_exit_decision",
            raw_input={
                "selected_symbol": (
                    str(selected.get("symbol") or "")
                    if isinstance(selected, dict)
                    else ""
                ),
                "selected_snapshot": (
                    {
                        "symbol": str(selected.get("symbol") or ""),
                        "score": selected.get("score"),
                        "risk_score": selected.get("risk_score"),
                        "confidence": selected.get("confidence"),
                    }
                    if isinstance(selected, dict)
                    else {}
                ),
                "open_position_count": int(open_position_count),
                "positions": {
                    str(k): {"qty": _to_int((v or {}).get("qty")), "avg_price": (v or {}).get("avg_price")}
                    for k, v in list(all_pos_map.items())[:20]
                },
                "monitor_policy": dict(monitor_policy),
                "strategist_guidance": {
                    "playbook": str(strategist_output.get("playbook") or ""),
                    "monitor_guidance": str(strategist_output.get("monitor_guidance") or ""),
                    "risk_tone": str(strategist_output.get("risk_tone") or ""),
                    "trade_aggressiveness": str(strategist_output.get("trade_aggressiveness") or ""),
                },
            },
            decision_link={"stage": "monitor_input_snapshot"},
        )
    except Exception:
        pass

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
    if bool(intents) and block_buy_open_position and open_position_count > 0:
        intents = []
        buy_blocked_open_position = True

    # Optional M29-2 exit policy (default disabled for backward compatibility).
    use_exit_policy = _resolve_use_exit_policy(state, policy)
    exit_policy_base = _resolve_exit_policy_config(policy)
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
        "position_age_seconds": None,
        "exit_signal_detected": False,
        "exit_confirm_count": 0,
        "min_hold_blocked": False,
        "sell_cooldown_blocked": False,
        "sell_cooldown_until": None,
        "pending_exit_lock_active": False,
        "pending_exit_lock_until": None,
        "monitor_reason": "hold",
        "emergency_exit": False,
    }
    if use_exit_policy and isinstance(selected, dict) and selected.get("symbol"):
        selected_symbol = _norm_symbol(selected.get("symbol"))
        pos_map = all_pos_map
        symbol = _select_exit_symbol(
            selected_symbol,
            pos_map,
            state=state,
            selected=selected,
            policy=policy,
            exit_policy_base=exit_policy_base,
        )
        selected_for_exit: Dict[str, Any] = selected
        if symbol and symbol != selected_symbol:
            selected_for_exit = {"symbol": symbol}
        features = selected_for_exit.get("features") if isinstance(selected_for_exit.get("features"), dict) else {}
        pos = pos_map.get(symbol, {})
        qty = max(0, _to_int(pos.get("qty")))
        # When a position is already held for monitored symbol, suppress fresh BUY intents.
        if qty > 0:
            intents = []
        decision = _preview_exit_decision_for_symbol(
            state=state,
            symbol=symbol,
            position=pos,
            selected=selected_for_exit,
            exit_policy_base=exit_policy_base,
        )
        avg_price = _to_float(decision.get("_avg_price"))
        price = decision.get("_price")
        hold_sec = _to_int(decision.get("_hold_sec"))
        now_epoch = _resolve_now_epoch(state)
        if hold_sec <= 0:
            persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
            last_trade_side = str(persisted.get("last_trade_side") or "").strip().upper()
            last_trade_epoch = _to_int(persisted.get("last_trade_epoch"))
            if last_trade_side == "BUY" and last_trade_epoch > 0:
                hold_sec = max(0, int(now_epoch - last_trade_epoch))
        min_hold_sec = _resolve_min_hold_sec(state, monitor_policy)
        sell_cooldown_sec = _resolve_sell_cooldown_sec(state, monitor_policy)
        confirm_ticks = _resolve_exit_confirm_ticks(state, monitor_policy)
        strategy_frame = _extract_monitor_strategy_frame(state)
        frame_applied = _apply_monitor_strategy_frame(
            min_hold_sec=min_hold_sec,
            sell_cooldown_sec=sell_cooldown_sec,
            confirm_ticks=confirm_ticks,
            frame=strategy_frame,
        )
        min_hold_sec = int(frame_applied.get("min_hold_sec") or min_hold_sec)
        sell_cooldown_sec = int(frame_applied.get("sell_cooldown_sec") or sell_cooldown_sec)
        confirm_ticks = int(frame_applied.get("confirm_ticks") or confirm_ticks)
        confirm_map = state.get("_monitor_exit_confirm")
        if not isinstance(confirm_map, dict):
            confirm_map = {}
        cooldown_map = state.get("_monitor_sell_cooldown_until")
        if not isinstance(cooldown_map, dict):
            cooldown_map = {}
        pending_exit_lock = state.get("_monitor_pending_exit_lock")
        if not isinstance(pending_exit_lock, dict):
            pending_exit_lock = {}
        prev_qty_map = state.get("_monitor_prev_position_qty")
        if not isinstance(prev_qty_map, dict):
            prev_qty_map = {}

        prev_qty = max(0, _to_int(prev_qty_map.get(symbol)))
        if prev_qty > 0 and qty <= 0 and sell_cooldown_sec > 0:
            cooldown_map[symbol] = int(now_epoch + sell_cooldown_sec)
        prev_qty_map[symbol] = int(qty)

        cooldown_until = max(0, _to_int(cooldown_map.get(symbol)))
        if cooldown_until > 0 and cooldown_until <= now_epoch:
            cooldown_map.pop(symbol, None)
            cooldown_until = 0

        lock_until = max(0, _to_int(pending_exit_lock.get(symbol)))
        if lock_until > 0 and lock_until <= now_epoch:
            pending_exit_lock.pop(symbol, None)
            lock_until = 0

        confirm_key = f"{symbol}:{str(decision.get('reason') or '').strip()}"
        confirm_count = 0
        sell_guard_blocked = False
        sell_guard_reason = ""
        monitor_reason = "hold"
        min_hold_blocked = False
        sell_cooldown_blocked = False
        exit_signal_detected = bool(decision.get("triggered"))
        emergency_exit = _is_emergency_exit_reason(str(decision.get("reason") or ""))
        hard_exit = _is_hard_exit_reason(str(decision.get("reason") or ""))

        if exit_signal_detected:
            if qty <= 0:
                sell_guard_blocked = True
                sell_guard_reason = "sell_guard_no_position"
                monitor_reason = "no_position"
            elif _is_trueish(state.get("execution_pending")):
                sell_guard_blocked = True
                sell_guard_reason = "sell_guard_execution_pending"
                monitor_reason = "pending_exit_lock"
            elif int(features.get("skill_open_orders") or 0) > 0:
                sell_guard_blocked = True
                sell_guard_reason = "sell_guard_open_order_pending"
                monitor_reason = "pending_exit_lock"
            elif lock_until > now_epoch:
                sell_guard_blocked = True
                sell_guard_reason = "sell_guard_pending_exit_lock"
                monitor_reason = "pending_exit_lock"
            elif not emergency_exit and not hard_exit and min_hold_sec > 0 and hold_sec > 0 and hold_sec < min_hold_sec:
                sell_guard_blocked = True
                min_hold_blocked = True
                sell_guard_reason = f"sell_guard_min_hold:{hold_sec}s<{min_hold_sec}s"
                monitor_reason = "min_hold_active"
            elif not emergency_exit and not hard_exit and sell_cooldown_sec > 0 and cooldown_until > now_epoch:
                sell_guard_blocked = True
                sell_cooldown_blocked = True
                sell_guard_reason = f"sell_guard_cooldown:{max(0, cooldown_until - now_epoch)}s_remaining"
                monitor_reason = "cooldown_active"
            elif not emergency_exit and not hard_exit and confirm_ticks > 1:
                confirm_count = _to_int(confirm_map.get(confirm_key)) + 1
                confirm_map[confirm_key] = int(confirm_count)
                if confirm_count < int(confirm_ticks):
                    sell_guard_blocked = True
                    sell_guard_reason = f"exit_confirmation_pending:{confirm_count}/{confirm_ticks}"
                    monitor_reason = "exit_signal_pending_confirmation"
            if not sell_guard_blocked and not monitor_reason:
                monitor_reason = "confirmed_exit_signal"
        else:
            _clear_symbol_confirm_keys(confirm_map, symbol)
            monitor_reason = "hold" if qty > 0 else "no_position"

        if not sell_guard_blocked and exit_signal_detected:
            _clear_symbol_confirm_keys(confirm_map, symbol)
            lock_sec = max(30, int(sell_cooldown_sec))
            pending_exit_lock[symbol] = int(now_epoch + lock_sec)
            lock_until = int(now_epoch + lock_sec)
            if sell_cooldown_sec > 0:
                cooldown_until = int(now_epoch + sell_cooldown_sec)
                cooldown_map[symbol] = int(cooldown_until)
            if emergency_exit:
                monitor_reason = "emergency_exit_signal"
            elif monitor_reason not in ("confirmed_exit_signal", "emergency_exit_signal"):
                monitor_reason = "confirmed_exit_signal"

        if qty <= 0:
            pending_exit_lock.pop(symbol, None)
            lock_until = 0

        state["_monitor_exit_confirm"] = confirm_map
        state["_monitor_sell_cooldown_until"] = cooldown_map
        state["_monitor_pending_exit_lock"] = pending_exit_lock
        state["_monitor_prev_position_qty"] = prev_qty_map

        exit_info = {
            "enabled": True,
            "evaluated": bool(decision.get("evaluated")),
            "triggered": bool(exit_signal_detected) and not bool(sell_guard_blocked),
            "reason": (
                str(sell_guard_reason)
                if str(sell_guard_reason).strip()
                else str(decision.get("reason") or "")
            ),
            "symbol": symbol,
            "selected_symbol": selected_symbol,
            "exit_symbol_fallback": bool(symbol and symbol != selected_symbol),
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
            "sell_cooldown_sec": int(sell_cooldown_sec),
            "exit_confirm_ticks": int(confirm_ticks),
            "exit_confirm_count": int(confirm_count),
            "sell_guard_blocked": bool(sell_guard_blocked),
            "sell_guard_reason": str(sell_guard_reason),
            "position_age_seconds": hold_sec if hold_sec > 0 else None,
            "exit_signal_detected": bool(exit_signal_detected),
            "min_hold_blocked": bool(min_hold_blocked),
            "sell_cooldown_blocked": bool(sell_cooldown_blocked),
            "sell_cooldown_until": (int(cooldown_until) if cooldown_until > 0 else None),
            "pending_exit_lock_active": bool(lock_until > now_epoch),
            "pending_exit_lock_until": (int(lock_until) if lock_until > 0 else None),
            "monitor_reason": str(monitor_reason or ""),
            "emergency_exit": bool(emergency_exit),
            "hard_exit": bool(hard_exit),
            "playbook": str(frame_applied.get("playbook") or ""),
            "monitor_guidance": str(frame_applied.get("monitor_guidance") or ""),
            "risk_tone": str(frame_applied.get("risk_tone") or ""),
            "trade_aggressiveness": str(frame_applied.get("trade_aggressiveness") or ""),
            "strategy_frame_adjustments": list(frame_applied.get("adjustments") or []),
        }
        if bool(exit_signal_detected) and not bool(sell_guard_blocked) and qty > 0:
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
                        "position_age_seconds": hold_sec if hold_sec > 0 else None,
                        "monitor_reason": str(monitor_reason or ""),
                        "exit_signal_detected": bool(exit_signal_detected),
                        "exit_confirm_count": int(confirm_count),
                        "min_hold_blocked": bool(min_hold_blocked),
                        "sell_cooldown_blocked": bool(sell_cooldown_blocked),
                        "emergency_exit": bool(emergency_exit),
                        "playbook": str(frame_applied.get("playbook") or ""),
                        "monitor_guidance": str(frame_applied.get("monitor_guidance") or ""),
                        "risk_tone": str(frame_applied.get("risk_tone") or ""),
                        "trade_aggressiveness": str(frame_applied.get("trade_aggressiveness") or ""),
                        "strategy_frame_adjustments": list(frame_applied.get("adjustments") or []),
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
        "exit_symbol_fallback": bool(exit_info.get("exit_symbol_fallback")),
        "exit_qty": int(exit_info.get("qty") or 0),
        "position_sizing_enabled": bool(sizing_info.get("enabled")),
        "position_sizing_evaluated": bool(sizing_info.get("evaluated")),
        "position_sizing_qty": int(sizing_info.get("qty") or 0),
        "position_sizing_reason": str(sizing_info.get("reason") or ""),
        "open_position_count": int(open_position_count),
        "block_buy_when_open_position": bool(block_buy_open_position),
        "buy_blocked_open_position": bool(buy_blocked_open_position),
    }
    state["monitor_output"] = {
        "selected_symbol": (selected.get("symbol") if isinstance(selected, dict) else None),
        "intent_side": (str(intents[0].get("side")) if intents else "NOOP"),
        "intent_qty": (int(intents[0].get("qty") or 0) if intents else 0),
        "entry_exit_reason": (
            str(exit_info.get("reason") or "")
            if bool(exit_info.get("enabled"))
            else (
                "buy_blocked_open_position"
                if bool(buy_blocked_open_position)
                else "entry_candidate_selected"
            )
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
            "monitor_reason": str(exit_info.get("monitor_reason") or ""),
            "exit_symbol_fallback": bool(exit_info.get("exit_symbol_fallback")),
            "playbook": str(exit_info.get("playbook") or ""),
            "monitor_guidance": str(exit_info.get("monitor_guidance") or ""),
            "risk_tone": str(exit_info.get("risk_tone") or ""),
            "trade_aggressiveness": str(exit_info.get("trade_aggressiveness") or ""),
            "position_sizing_enabled": bool(sizing_info.get("enabled")),
            "position_sizing_evaluated": bool(sizing_info.get("evaluated")),
            "position_sizing_qty": int(sizing_info.get("qty") or 0),
            "position_sizing_reason": str(sizing_info.get("reason") or ""),
            "open_position_count": int(open_position_count),
            "block_buy_when_open_position": bool(block_buy_open_position),
            "buy_blocked_open_position": bool(buy_blocked_open_position),
        },
    )
    append_decision_trace(
        state,
        agent="monitor",
        event="entry_exit_decision",
        payload={
            "entry_reason": str((state.get("monitor_output") or {}).get("entry_exit_reason") or ""),
            "exit_reason": str(exit_info.get("reason") or ""),
            "position_age_seconds": exit_info.get("position_age_seconds"),
            "min_hold_blocked": bool(exit_info.get("min_hold_blocked")),
            "sell_cooldown_blocked": bool(exit_info.get("sell_cooldown_blocked")),
            "monitor_reason": str(exit_info.get("monitor_reason") or ""),
            "exit_symbol_fallback": bool(exit_info.get("exit_symbol_fallback")),
            "playbook": str(exit_info.get("playbook") or ""),
            "monitor_guidance": str(exit_info.get("monitor_guidance") or ""),
            "risk_tone": str(exit_info.get("risk_tone") or ""),
            "trade_aggressiveness": str(exit_info.get("trade_aggressiveness") or ""),
        },
    )
    try:
        record_decision_bridge(
            run_id=run_id,
            agent="monitor",
            stage="decision_bridge",
            raw_input={
                "selected_symbol": (
                    str(selected.get("symbol") or "")
                    if isinstance(selected, dict)
                    else ""
                ),
                "monitor_policy": dict(monitor_policy),
                "intents_preview": [
                    {
                        "symbol": str(x.get("symbol") or ""),
                        "side": str(x.get("side") or ""),
                        "qty": _to_int(x.get("qty")),
                    }
                    for x in list(intents)[:3]
                    if isinstance(x, dict)
                ],
            },
            parsed_output={
                "entry_reason": str((state.get("monitor_output") or {}).get("entry_exit_reason") or ""),
                "exit_reason": str(exit_info.get("reason") or ""),
                "monitor_reason": str(exit_info.get("monitor_reason") or ""),
                "position_age_seconds": exit_info.get("position_age_seconds"),
                "exit_signal_detected": bool(exit_info.get("exit_signal_detected")),
                "min_hold_blocked": bool(exit_info.get("min_hold_blocked")),
                "sell_cooldown_blocked": bool(exit_info.get("sell_cooldown_blocked")),
            },
            decision_link={
                "decision_chain": {
                    "theme": str((state.get("themes") or [""])[0] if isinstance(state.get("themes"), list) and state.get("themes") else ""),
                    "scanner_selected": state.get("top_stock") or (
                        str(selected.get("symbol") or "") if isinstance(selected, dict) else ""
                    ),
                    "entry_reason": str((state.get("monitor_output") or {}).get("entry_exit_reason") or ""),
                    "exit_reason": str(exit_info.get("reason") or ""),
                }
            },
        )
    except Exception:
        pass
    return state
