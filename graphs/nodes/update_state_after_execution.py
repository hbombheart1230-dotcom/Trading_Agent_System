from __future__ import annotations

import os
import re
import time

from libs.core.symbols import normalize_symbol
from libs.reporting.reasoning_trace import build_reasoning_provenance, build_reasoning_trace_from_summaries
from libs.runtime.position_horizon_revision import initialize_horizon_state
from libs.runtime.same_symbol_loss_reentry import record_same_symbol_exit

POST_EXIT_SHADOW_WATCH_WINDOW_SEC = 90 * 60


def _as_int(value, default: int = 0) -> int:  # type: ignore[no-untyped-def]
    try:
        return int(float(value))
    except Exception:
        return default


def _as_float(value, default: float = 0.0) -> float:  # type: ignore[no-untyped-def]
    try:
        return float(value)
    except Exception:
        return default


def _as_ratio(value):  # type: ignore[no-untyped-def]
    if value in (None, ""):
        return None
    try:
        out = float(value)
    except Exception:
        return None
    if abs(out) > 1.0:
        out = out / 100.0
    return float(out)


def _normalize_mock_positions(raw):  # type: ignore[no-untyped-def]
    out = []
    if not isinstance(raw, list):
        return out
    for row in raw:
        if not isinstance(row, dict):
            continue
        symbol = normalize_symbol(row.get("symbol"))
        qty = _as_int(row.get("qty"), 0)
        if not symbol or qty <= 0:
            continue
        out.append(
            {
                "symbol": symbol,
                "qty": qty,
                "avg_price": _as_float(row.get("avg_price"), 0.0),
                "unrealized_pnl": _as_float(row.get("unrealized_pnl"), 0.0),
            }
        )
        account_pnl_ratio = _as_ratio(
            row.get("account_pnl_ratio")
            if row.get("account_pnl_ratio") not in (None, "")
            else row.get("unrealized_pnl_rate")
        )
        if account_pnl_ratio is not None:
            out[-1]["account_pnl_ratio"] = float(account_pnl_ratio)
            out[-1]["account_pnl_ratio_source"] = str(
                row.get("account_pnl_ratio_source") or "position.account_pnl_ratio"
            ).strip()
        current_price = _as_float(
            row.get("current_price") if row.get("current_price") not in (None, "") else row.get("cur_price"),
            0.0,
        )
        if current_price > 0.0:
            out[-1]["current_price"] = float(current_price)
        entry_epoch = _as_int(
            row.get("position_entry_epoch")
            if row.get("position_entry_epoch") not in (None, "")
            else row.get("entry_epoch"),
            0,
        )
        if entry_epoch > 0:
            out[-1]["position_entry_epoch"] = int(entry_epoch)
        hold_sec = _as_int(
            row.get("hold_sec")
            if row.get("hold_sec") not in (None, "")
            else row.get("position_age_seconds"),
            0,
        )
        if hold_sec > 0:
            out[-1]["hold_sec"] = int(hold_sec)
            out[-1]["position_age_seconds"] = int(hold_sec)
    return out


def _normalize_position_peak_price(raw, open_symbols=None):  # type: ignore[no-untyped-def]
    out = {}
    allowed = None
    if isinstance(open_symbols, (list, set, tuple)):
        allowed = {normalize_symbol(sym) for sym in open_symbols if normalize_symbol(sym)}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        symbol = normalize_symbol(key)
        if not symbol:
            continue
        if allowed is not None and symbol not in allowed:
            continue
        peak = _as_float(value, 0.0)
        if peak > 0.0:
            out[symbol] = float(peak)
    return out


def _sanitize_closeout_unresolved_flatten_state(ps: dict) -> None:
    open_symbols = {
        normalize_symbol(row.get("symbol"))
        for row in list(ps.get("mock_positions") or [])
        if isinstance(row, dict) and normalize_symbol(row.get("symbol")) and _as_int(row.get("qty"), 0) > 0
    }
    unresolved_map = ps.get("closeout_unresolved_flatten_by_symbol")
    if isinstance(unresolved_map, dict):
        filtered_map = {
            normalize_symbol(key): value
            for key, value in unresolved_map.items()
            if normalize_symbol(key) in open_symbols
        }
        if filtered_map:
            ps["closeout_unresolved_flatten_by_symbol"] = filtered_map
        else:
            ps.pop("closeout_unresolved_flatten_by_symbol", None)

    closeout = ps.get("closeout_backup_liquidation")
    if not isinstance(closeout, dict):
        return
    unresolved = [
        symbol
        for symbol in (normalize_symbol(x) for x in list(closeout.get("unresolved_flatten_symbols") or []))
        if symbol and symbol in open_symbols
    ]
    closeout["unresolved_flatten_symbols"] = list(unresolved)
    closeout["unresolved_flatten_requires_next_open_symbols"] = list(unresolved)
    closeout["requires_next_open_flatten"] = bool(unresolved)
    if not unresolved and str(closeout.get("mode") or "") == "broker_truth_unresolved_positions_retained":
        closeout["mode"] = "broker_truth_unresolved_positions_cleared"
        closeout["reason"] = "closeout_unresolved_positions_cleared_after_sell"
        closeout["symbols"] = []
        closeout["qty_total"] = 0
    ps["closeout_backup_liquidation"] = closeout


def _normalize_position_entry_epoch_map(raw, open_symbols=None):  # type: ignore[no-untyped-def]
    out = {}
    allowed = None
    if isinstance(open_symbols, (list, set, tuple)):
        allowed = {normalize_symbol(sym) for sym in open_symbols if normalize_symbol(sym)}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        symbol = normalize_symbol(key)
        if not symbol:
            continue
        if allowed is not None and symbol not in allowed:
            continue
        epoch = _as_int(value, 0)
        if epoch > 0:
            out[symbol] = int(epoch)
    return out


def _normalize_position_entry_risk_map(raw, open_symbols=None):  # type: ignore[no-untyped-def]
    out = {}
    allowed = None
    if isinstance(open_symbols, (list, set, tuple)):
        allowed = {normalize_symbol(sym) for sym in open_symbols if normalize_symbol(sym)}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        symbol = normalize_symbol(key)
        if not symbol:
            continue
        if allowed is not None and symbol not in allowed:
            continue
        if not isinstance(value, dict):
            continue
        stop_loss_pct = _as_float(value.get("stop_loss_pct"), 0.0)
        if stop_loss_pct <= 0.0:
            continue
        row = {
            "symbol": symbol,
            "stop_loss_pct": float(stop_loss_pct),
            "source": str(value.get("source") or "entry_sizing").strip(),
        }
        for src_key, dst_key in (
            ("stop_loss_source", "stop_loss_source"),
            ("invalidation_price", "invalidation_price"),
            ("raw_structure_stop_loss_pct", "raw_structure_stop_loss_pct"),
            ("min_structure_stop_loss_pct", "min_structure_stop_loss_pct"),
            ("sizing_price", "sizing_price"),
            ("risk_budget", "risk_budget"),
            ("notional_budget", "notional_budget"),
            ("qty_by_risk", "qty_by_risk"),
            ("qty_by_notional", "qty_by_notional"),
            ("recorded_epoch", "recorded_epoch"),
        ):
            raw_value = value.get(src_key)
            if raw_value in (None, ""):
                continue
            if src_key in {"stop_loss_source", "source"}:
                row[dst_key] = str(raw_value).strip()
            elif src_key in {"qty_by_risk", "qty_by_notional", "recorded_epoch"}:
                row[dst_key] = _as_int(raw_value, 0)
            else:
                row[dst_key] = float(_as_float(raw_value, 0.0))
        out[symbol] = row
    return out


def _extract_entry_risk_from_order(order: dict, *, symbol: str, now_epoch: int) -> dict:  # type: ignore[no-untyped-def]
    meta = order.get("meta") if isinstance(order.get("meta"), dict) else {}
    sizing = meta.get("sizing") if isinstance(meta.get("sizing"), dict) else {}
    inputs = sizing.get("inputs") if isinstance(sizing.get("inputs"), dict) else {}
    stop_loss_pct = _as_float(
        inputs.get("stop_loss_pct")
        if inputs.get("stop_loss_pct") not in (None, "")
        else meta.get("position_sizing_stop_loss_pct"),
        0.0,
    )
    if stop_loss_pct <= 0.0:
        return {}
    row = {
        "symbol": symbol,
        "stop_loss_pct": float(stop_loss_pct),
        "stop_loss_source": str(
            inputs.get("stop_loss_source") or meta.get("position_sizing_stop_loss_source") or "entry_sizing"
        ).strip(),
        "source": "buy_execution_sizing",
        "recorded_epoch": int(now_epoch),
    }
    for key in (
        "invalidation_price",
        "raw_structure_stop_loss_pct",
        "min_structure_stop_loss_pct",
        "risk_budget",
        "notional_budget",
        "qty_by_risk",
        "qty_by_notional",
    ):
        raw = inputs.get(key)
        if raw in (None, ""):
            continue
        if key in {"qty_by_risk", "qty_by_notional"}:
            row[key] = _as_int(raw, 0)
        else:
            row[key] = float(_as_float(raw, 0.0))
    sizing_price = _as_float(sizing.get("price") if sizing.get("price") not in (None, "") else inputs.get("price"), 0.0)
    if sizing_price > 0.0:
        row["sizing_price"] = float(sizing_price)
    return row


def _remember_position_entry_risk_progress(ps: dict, ex: dict, *, now_epoch: int) -> None:
    side = _extract_trade_side(ex)
    order = ex.get("order") if isinstance(ex.get("order"), dict) else {}
    symbol = normalize_symbol(order.get("symbol") or order.get("stk_cd"))
    if not symbol or side not in {"BUY", "SELL"}:
        return
    risk_map = _normalize_position_entry_risk_map(ps.get("position_entry_risk_by_symbol"))
    if side == "BUY":
        row = _extract_entry_risk_from_order(order, symbol=symbol, now_epoch=now_epoch)
        if row:
            risk_map[symbol] = row
    else:
        meta = order.get("meta") if isinstance(order.get("meta"), dict) else {}
        partial_exit = str(meta.get("partial_exit") or "").strip().lower() in ("1", "true", "yes", "y", "on")
        exit_qty = _as_int(meta.get("exit_qty") or order.get("qty"), 0)
        position_qty = _as_int(meta.get("position_qty"), 0)
        if (not partial_exit) or (position_qty > 0 and exit_qty >= position_qty):
            risk_map.pop(symbol, None)
    if risk_map:
        ps["position_entry_risk_by_symbol"] = risk_map
    else:
        ps.pop("position_entry_risk_by_symbol", None)


def _normalize_position_strategy_context(raw, open_symbols=None):  # type: ignore[no-untyped-def]
    out = {}
    allowed = None
    if isinstance(open_symbols, (list, set, tuple)):
        allowed = {normalize_symbol(sym) for sym in open_symbols if normalize_symbol(sym)}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        symbol = normalize_symbol(key)
        if not symbol:
            continue
        if allowed is not None and symbol not in allowed:
            continue
        if not isinstance(value, dict):
            continue
        output = value.get("output") if isinstance(value.get("output"), dict) else {}
        if not output:
            continue
        row = dict(value)
        row["output"] = dict(output)
        out[symbol] = row
    return out


def _default_mock_cash() -> float:
    raw = str(os.getenv("MOCK_CASH_FALLBACK", "2000000") or "2000000").strip()
    v = _as_float(raw, 2000000.0)
    return v if v > 0.0 else 2000000.0


def _is_kiwoom_mock_mode() -> bool:
    return str(os.getenv("KIWOOM_MODE", "mock") or "mock").strip().lower() == "mock"


def _ensure_mock_cash(ps: dict) -> float:
    cur = _as_float(ps.get("mock_cash"), 0.0)
    if cur > 0.0:
        return cur
    base = _default_mock_cash()
    ps["mock_cash"] = float(base)
    return float(base)


def _current_session_date() -> str:
    return str(time.strftime("%Y-%m-%d") or "").strip()


def _normalize_mock_broker_restricted_symbols(raw, active_date: str | None = None):  # type: ignore[no-untyped-def]
    out = {}
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        row = dict(value) if isinstance(value, dict) else {}
        symbol = normalize_symbol(row.get("symbol") or key)
        if not symbol:
            continue
        detected_date = str(row.get("detected_date") or "").strip()
        if active_date and detected_date and detected_date != active_date:
            continue
        out[symbol] = {
            "symbol": symbol,
            "broker_code": str(row.get("broker_code") or "").strip(),
            "broker_message": str(row.get("broker_message") or "").strip(),
            "reason": str(row.get("reason") or "").strip(),
            "detected_epoch": _as_int(row.get("detected_epoch"), 0),
            "detected_date": detected_date,
        }
    return out


def _resolve_mock_fill_price(state: dict, ex: dict, symbol: str) -> float:
    order = ex.get("order") if isinstance(ex.get("order"), dict) else {}
    payload = ex.get("payload") if isinstance(ex.get("payload"), dict) else {}

    candidates = [
        order.get("price"),
        order.get("avg_fill_price"),
        order.get("fill_price"),
        payload.get("avg_fill_price"),
        payload.get("fill_price"),
        payload.get("executed_price"),
        payload.get("price"),
    ]

    selected = state.get("selected") if isinstance(state.get("selected"), dict) else {}
    if normalize_symbol(selected.get("symbol")) == symbol:
        features = selected.get("features") if isinstance(selected.get("features"), dict) else {}
        candidates.extend(
            [
                selected.get("price"),
                features.get("skill_quote_price"),
                features.get("current_price"),
                features.get("last_price"),
            ]
        )

    market = state.get("market_snapshot") if isinstance(state.get("market_snapshot"), dict) else {}
    if normalize_symbol(market.get("symbol")) in ("", symbol):
        candidates.extend(
            [
                market.get("price"),
                market.get("cur_price"),
                market.get("last_price"),
                market.get("current_price"),
            ]
        )

    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    candidates.extend(
        [
            persisted.get("last_market_price"),
            persisted.get("last_price"),
        ]
    )

    for value in candidates:
        px = _as_float(value, 0.0)
        if px > 0.0:
            return float(px)
    return 0.0


def _execution_fill_quantity_snapshot(ex: dict) -> dict:
    payload = ex.get("payload") if isinstance(ex.get("payload"), dict) else {}
    containers = [
        ex,
        payload,
        ex.get("order_status") if isinstance(ex.get("order_status"), dict) else {},
        payload.get("order_status") if isinstance(payload.get("order_status"), dict) else {},
        ex.get("broker_result") if isinstance(ex.get("broker_result"), dict) else {},
        payload.get("broker_result") if isinstance(payload.get("broker_result"), dict) else {},
        ex.get("response_payload") if isinstance(ex.get("response_payload"), dict) else {},
        payload.get("response_payload") if isinstance(payload.get("response_payload"), dict) else {},
    ]

    def first_value(*keys):  # type: ignore[no-untyped-def]
        for container in containers:
            if not isinstance(container, dict):
                continue
            for key in keys:
                if container.get(key) not in (None, ""):
                    return container.get(key), key
        return None, ""

    filled_raw, filled_key = first_value("filled_qty", "cntr_qty", "exec_qty")
    remaining_raw, remaining_key = first_value("remaining_qty", "ord_remnq", "rmnd_qty", "unfilled_qty", "unfilled")
    order_raw, order_key = first_value("order_qty", "ord_qty", "qty")
    filled_qty = max(0, _as_int(filled_raw, 0)) if filled_raw not in (None, "") else None
    remaining_qty = max(0, _as_int(remaining_raw, 0)) if remaining_raw not in (None, "") else None
    order_qty = max(0, _as_int(order_raw, 0)) if order_raw not in (None, "") else None
    return {
        "has_fill_truth": bool(filled_raw not in (None, "") or remaining_raw not in (None, "")),
        "filled_qty": filled_qty,
        "remaining_qty": remaining_qty,
        "order_qty": order_qty,
        "filled_qty_source": filled_key,
        "remaining_qty_source": remaining_key,
        "order_qty_source": order_key,
        "pending_unfilled": bool((filled_qty or 0) <= 0 and remaining_qty is not None and remaining_qty > 0),
    }


def _is_zero_fill_truth_pending(snapshot: dict, side: str) -> bool:
    if str(side or "").strip().upper() not in ("BUY", "SELL"):
        return False
    if not bool(snapshot.get("has_fill_truth")):
        return False
    filled_qty = _as_int(snapshot.get("filled_qty"), 0)
    if filled_qty > 0:
        return False
    remaining_qty = snapshot.get("remaining_qty")
    if remaining_qty is None:
        return True
    return _as_int(remaining_qty, 0) > 0


def _remember_pending_unfilled_order(ps: dict, ex: dict, order: dict, snapshot: dict, *, now_epoch: int | None = None) -> None:
    symbol = normalize_symbol(order.get("symbol") or order.get("stk_cd"))
    action = str(order.get("action") or "").strip().upper()
    if not symbol or action not in ("BUY", "SELL"):
        return
    payload = ex.get("payload") if isinstance(ex.get("payload"), dict) else {}
    pending = ps.get("pending_unfilled_orders") if isinstance(ps.get("pending_unfilled_orders"), dict) else {}
    pending[symbol] = {
        "symbol": symbol,
        "action": action,
        "order_id": str(ex.get("order_id") or ex.get("ord_no") or payload.get("order_id") or payload.get("ord_no") or ""),
        "order_qty": int(snapshot.get("order_qty") or _as_int(order.get("qty"), 0)),
        "filled_qty": int(snapshot.get("filled_qty") or 0),
        "remaining_qty": int(snapshot.get("remaining_qty") or 0),
        "recorded_epoch": int(now_epoch if now_epoch is not None else time.time()),
        "source": "execution_fill_quantity_snapshot",
    }
    ps["pending_unfilled_orders"] = pending


def _resolve_post_exit_watch_exit_price(state: dict, ex: dict, symbol: str) -> tuple[float, str]:
    order = ex.get("order") if isinstance(ex.get("order"), dict) else {}
    payload = ex.get("payload") if isinstance(ex.get("payload"), dict) else {}
    broker_result = ex.get("broker_result") if isinstance(ex.get("broker_result"), dict) else {}
    payload_broker_result = (
        payload.get("broker_result")
        if isinstance(payload.get("broker_result"), dict)
        else {}
    )
    candidates = [
        ("payload.filled_price", payload.get("filled_price")),
        ("payload.avg_price", payload.get("avg_price")),
        ("payload.broker_fill_price", payload.get("broker_fill_price")),
        ("payload.cntr_uv", payload.get("cntr_uv")),
        ("payload.avg_fill_price", payload.get("avg_fill_price")),
        ("payload.fill_price", payload.get("fill_price")),
        ("payload.executed_price", payload.get("executed_price")),
        ("order.filled_price", order.get("filled_price")),
        ("order.avg_price", order.get("avg_price")),
        ("order.avg_fill_price", order.get("avg_fill_price")),
        ("order.fill_price", order.get("fill_price")),
        ("broker_result.filled_price", broker_result.get("filled_price")),
        ("broker_result.avg_price", broker_result.get("avg_price")),
        ("broker_result.cntr_uv", broker_result.get("cntr_uv")),
        ("broker_result.price", broker_result.get("price")),
        ("payload.broker_result.filled_price", payload_broker_result.get("filled_price")),
        ("payload.broker_result.avg_price", payload_broker_result.get("avg_price")),
        ("payload.broker_result.cntr_uv", payload_broker_result.get("cntr_uv")),
        ("payload.broker_result.price", payload_broker_result.get("price")),
    ]
    for source, value in candidates:
        px = _as_float(value, 0.0)
        if px > 0.0:
            return float(px), source
    fallback = _resolve_mock_fill_price(state, ex, symbol)
    if fallback > 0.0:
        return float(fallback), "fallback.mock_fill_price"
    return 0.0, ""


def _apply_mock_fill(ps: dict, ex: dict, state: dict | None = None) -> None:
    order = ex.get("order") if isinstance(ex.get("order"), dict) else {}
    action = str(order.get("action") or "").strip().upper()
    symbol = normalize_symbol(order.get("symbol"))
    qty = _as_int(order.get("qty"), 0)
    price = _as_float(order.get("price"), 0.0)
    if price <= 0.0 and isinstance(state, dict):
        price = _resolve_mock_fill_price(state, ex, symbol)
    fill_snapshot = _execution_fill_quantity_snapshot(ex)
    if qty <= 0 and _as_int(fill_snapshot.get("filled_qty"), 0) > 0:
        qty = _as_int(fill_snapshot.get("filled_qty"), 0)
    if action not in ("BUY", "SELL") or not symbol or qty <= 0:
        return
    if bool(fill_snapshot.get("pending_unfilled")) or _is_zero_fill_truth_pending(fill_snapshot, action):
        _remember_pending_unfilled_order(ps, ex, order, fill_snapshot)
        return
    filled_qty = _as_int(fill_snapshot.get("filled_qty"), 0)
    if bool(fill_snapshot.get("has_fill_truth")) and filled_qty > 0:
        qty = min(qty, filled_qty)

    pos = _normalize_mock_positions(ps.get("mock_positions"))
    by_symbol = {str(r.get("symbol")): dict(r) for r in pos if isinstance(r, dict)}
    peak_map = _normalize_position_peak_price(ps.get("position_peak_price"), by_symbol.keys())
    strategy_context_map = _normalize_position_strategy_context(ps.get("position_strategy_context"), by_symbol.keys())
    entry_epoch_map = _normalize_position_entry_epoch_map(ps.get("position_entry_epoch_by_symbol"), by_symbol.keys())
    entry_risk_map = _normalize_position_entry_risk_map(ps.get("position_entry_risk_by_symbol"), by_symbol.keys())
    for sym, row in by_symbol.items():
        row_epoch = _as_int(row.get("position_entry_epoch"), 0)
        if row_epoch > 0 and _as_int(entry_epoch_map.get(sym), 0) <= 0:
            entry_epoch_map[sym] = int(row_epoch)
    cur = dict(by_symbol.get(symbol) or {"symbol": symbol, "qty": 0, "avg_price": 0.0, "unrealized_pnl": 0.0})
    cash = _ensure_mock_cash(ps)
    realized_total = _as_float(ps.get("mock_realized_pnl"), 0.0)
    now_epoch = _as_int(time.time(), 0)

    if action == "BUY":
        pending_orders = ps.get("pending_unfilled_orders") if isinstance(ps.get("pending_unfilled_orders"), dict) else {}
        pending_orders.pop(symbol, None)
        if pending_orders:
            ps["pending_unfilled_orders"] = pending_orders
        else:
            ps.pop("pending_unfilled_orders", None)
        prev_qty = _as_int(cur.get("qty"), 0)
        prev_avg = _as_float(cur.get("avg_price"), 0.0)
        new_qty = prev_qty + qty
        if new_qty <= 0:
            return
        if price > 0.0:
            cash -= float(qty) * float(price)
        if price > 0:
            weighted_avg = ((prev_qty * prev_avg) + (qty * price)) / float(new_qty)
        else:
            weighted_avg = prev_avg
        cur["qty"] = new_qty
        cur["avg_price"] = float(weighted_avg)
        by_symbol[symbol] = cur
        if prev_qty <= 0 or _as_int(entry_epoch_map.get(symbol), 0) <= 0:
            entry_epoch_map[symbol] = int(now_epoch)
        next_peak = max(_as_float(peak_map.get(symbol), 0.0), float(weighted_avg), float(price))
        if next_peak > 0.0:
            peak_map[symbol] = float(next_peak)
        strategy_snapshot = _extract_order_strategy_snapshot(order) or _extract_strategist_output_snapshot(state)
        if strategy_snapshot:
            controlled_lane = bool(strategy_snapshot.get("controlled_mock_lane"))
            strategy_context_map[symbol] = {
                "output": dict(strategy_snapshot),
                "generated_epoch": _as_int(time.time(), 0),
                "source": (
                    "controlled_mock_lane_buy_execution"
                    if controlled_lane
                    else "buy_execution"
                ),
                "horizon_state": initialize_horizon_state(
                    strategy_snapshot,
                    now_epoch=now_epoch,
                ),
                "horizon_revision_allowed": bool(
                    strategy_snapshot.get("horizon_revision_allowed", True)
                ),
            }
        entry_risk = _extract_entry_risk_from_order(order, symbol=symbol, now_epoch=now_epoch)
        if entry_risk:
            entry_risk_map[symbol] = entry_risk
    else:
        pending_orders = ps.get("pending_unfilled_orders") if isinstance(ps.get("pending_unfilled_orders"), dict) else {}
        pending_orders.pop(symbol, None)
        if pending_orders:
            ps["pending_unfilled_orders"] = pending_orders
        else:
            ps.pop("pending_unfilled_orders", None)
        prev_qty = _as_int(cur.get("qty"), 0)
        if prev_qty <= 0:
            return
        fill_qty = min(prev_qty, qty)
        if fill_qty <= 0:
            return
        prev_avg = _as_float(cur.get("avg_price"), 0.0)
        if price > 0.0:
            cash += float(fill_qty) * float(price)
            realized_total += float(fill_qty) * (float(price) - float(prev_avg))
        new_qty = max(0, prev_qty - fill_qty)
        if new_qty <= 0:
            by_symbol.pop(symbol, None)
            peak_map.pop(symbol, None)
            strategy_context_map.pop(symbol, None)
            entry_epoch_map.pop(symbol, None)
            entry_risk_map.pop(symbol, None)
        else:
            cur["qty"] = new_qty
            by_symbol[symbol] = cur

    final_positions = [v for v in by_symbol.values() if _as_int(v.get("qty"), 0) > 0]
    final_symbols = [row.get("symbol") for row in final_positions]
    final_entry_epoch_map = _normalize_position_entry_epoch_map(entry_epoch_map, final_symbols)
    for row in final_positions:
        sym = normalize_symbol(row.get("symbol"))
        entry_epoch = _as_int(final_entry_epoch_map.get(sym), 0)
        if entry_epoch > 0:
            row["position_entry_epoch"] = int(entry_epoch)
    ps["mock_positions"] = final_positions
    ps["open_positions"] = len(final_positions)
    ps["mock_cash"] = float(cash)
    ps["mock_realized_pnl"] = float(realized_total)
    final_peak_map = _normalize_position_peak_price(peak_map, [row.get("symbol") for row in final_positions])
    if final_peak_map:
        ps["position_peak_price"] = final_peak_map
    else:
        ps.pop("position_peak_price", None)
    final_strategy_context_map = _normalize_position_strategy_context(
        strategy_context_map,
        [row.get("symbol") for row in final_positions],
    )
    if final_strategy_context_map:
        ps["position_strategy_context"] = final_strategy_context_map
    else:
        ps.pop("position_strategy_context", None)
    if final_entry_epoch_map:
        ps["position_entry_epoch_by_symbol"] = final_entry_epoch_map
    else:
        ps.pop("position_entry_epoch_by_symbol", None)
    final_entry_risk_map = _normalize_position_entry_risk_map(
        entry_risk_map,
        [row.get("symbol") for row in final_positions],
    )
    if final_entry_risk_map:
        ps["position_entry_risk_by_symbol"] = final_entry_risk_map
    else:
        ps.pop("position_entry_risk_by_symbol", None)


def _extract_trade_side(ex: dict) -> str:
    order = ex.get("order") if isinstance(ex.get("order"), dict) else {}
    side = str(order.get("action") or "").strip().upper()
    if side in ("BUY", "SELL"):
        return side
    return ""


def _normalize_post_exit_shadow_watchlist(raw, *, now_epoch: int = 0):  # type: ignore[no-untyped-def]
    rows = []
    if isinstance(raw, dict):
        rows = list(raw.values())
    elif isinstance(raw, list):
        rows = list(raw)
    out = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = normalize_symbol(row.get("symbol"))
        if not symbol:
            continue
        exit_epoch = _as_int(row.get("exit_epoch") or row.get("sold_epoch") or row.get("ts"), 0)
        if exit_epoch <= 0:
            continue
        expires_epoch = _as_int(row.get("expires_epoch"), exit_epoch + POST_EXIT_SHADOW_WATCH_WINDOW_SEC)
        if now_epoch > 0 and expires_epoch > 0 and now_epoch > expires_epoch:
            continue
        normalized = dict(row)
        normalized["symbol"] = symbol
        normalized["exit_epoch"] = int(exit_epoch)
        normalized["expires_epoch"] = int(expires_epoch)
        normalized["observability_only"] = True
        out[symbol] = normalized
    return out


def _remember_post_exit_shadow_watch(ps: dict, ex: dict, state: dict, *, now_epoch: int) -> None:
    side = _extract_trade_side(ex)
    order = ex.get("order") if isinstance(ex.get("order"), dict) else {}
    symbol = normalize_symbol(order.get("symbol") or order.get("stk_cd"))
    if not symbol:
        return
    watchlist = _normalize_post_exit_shadow_watchlist(
        ps.get("post_exit_shadow_watchlist"),
        now_epoch=int(now_epoch),
    )
    if side == "BUY":
        watchlist.pop(symbol, None)
    elif side == "SELL":
        payload = ex.get("payload") if isinstance(ex.get("payload"), dict) else {}
        exit_price, exit_price_source = _resolve_post_exit_watch_exit_price(state, ex, symbol)
        qty = _as_int(order.get("qty") or payload.get("qty") or payload.get("filled_qty"), 0)
        row = {
            "schema_version": "post_exit_shadow_watch.v1",
            "observability_only": True,
            "symbol": symbol,
            "exit_epoch": int(now_epoch),
            "exit_price": float(exit_price) if exit_price > 0.0 else None,
            "exit_price_source": str(exit_price_source or ""),
            "qty": int(qty) if qty > 0 else None,
            "created_epoch": int(now_epoch),
            "last_refresh_epoch": 0,
            "latest_candle_ts": None,
            "expires_epoch": int(now_epoch + POST_EXIT_SHADOW_WATCH_WINDOW_SEC),
            "source": "execution_sell",
        }
        trade_id = str(payload.get("trade_id") or state.get("trade_id") or "").strip()
        if trade_id:
            row["trade_id"] = trade_id
        watchlist[symbol] = row
    if watchlist:
        ps["post_exit_shadow_watchlist"] = watchlist
    else:
        ps.pop("post_exit_shadow_watchlist", None)


def _remember_profit_take_progress(ps: dict, ex: dict, *, now_epoch: int) -> None:
    side = _extract_trade_side(ex)
    order = ex.get("order") if isinstance(ex.get("order"), dict) else {}
    symbol = normalize_symbol(order.get("symbol") or order.get("stk_cd"))
    if not symbol:
        return
    if side == "BUY":
        partial_map = ps.get("partial_take_profit_taken_by_symbol")
        if isinstance(partial_map, dict):
            partial_map.pop(symbol, None)
            if partial_map:
                ps["partial_take_profit_taken_by_symbol"] = partial_map
            else:
                ps.pop("partial_take_profit_taken_by_symbol", None)
        ladder_map = ps.get("profit_ladder_taken_levels_by_symbol")
        if isinstance(ladder_map, dict):
            ladder_map.pop(symbol, None)
            if ladder_map:
                ps["profit_ladder_taken_levels_by_symbol"] = ladder_map
            else:
                ps.pop("profit_ladder_taken_levels_by_symbol", None)
        rr_map = ps.get("risk_reward_take_profit_taken_rungs_by_symbol")
        if isinstance(rr_map, dict):
            rr_map.pop(symbol, None)
            if rr_map:
                ps["risk_reward_take_profit_taken_rungs_by_symbol"] = rr_map
            else:
                ps.pop("risk_reward_take_profit_taken_rungs_by_symbol", None)
        return
    if side != "SELL":
        return
    meta = order.get("meta") if isinstance(order.get("meta"), dict) else {}
    reason = str(meta.get("exit_reason") or meta.get("reason") or order.get("reason") or "").strip()
    if reason == "partial_take_profit":
        partial_map = ps.get("partial_take_profit_taken_by_symbol")
        if not isinstance(partial_map, dict):
            partial_map = {}
        partial_map[symbol] = {
            "symbol": symbol,
            "taken_epoch": int(now_epoch),
            "exit_qty": _as_int(meta.get("exit_qty") or order.get("qty"), 0),
            "position_qty": _as_int(meta.get("position_qty"), 0),
            "pnl_ratio": _as_float(meta.get("pnl_ratio"), 0.0),
            "source": "execution_sell",
        }
        ps["partial_take_profit_taken_by_symbol"] = partial_map
    if reason == "profit_ladder":
        level = _as_float(meta.get("profit_ladder_level_pct"), 0.0)
        if level > 0.0:
            ladder_map = ps.get("profit_ladder_taken_levels_by_symbol")
            if not isinstance(ladder_map, dict):
                ladder_map = {}
            levels = [
                _as_float(x, 0.0)
                for x in list(ladder_map.get(symbol) or [])
                if _as_float(x, 0.0) > 0.0
            ]
            if round(level, 6) not in {round(x, 6) for x in levels}:
                levels.append(float(level))
            ladder_map[symbol] = sorted(levels)
            ps["profit_ladder_taken_levels_by_symbol"] = ladder_map
    if reason == "risk_reward_take_profit":
        rung = _as_float(meta.get("risk_reward_take_profit_rung"), 0.0)
        if rung > 0.0:
            rr_map = ps.get("risk_reward_take_profit_taken_rungs_by_symbol")
            if not isinstance(rr_map, dict):
                rr_map = {}
            rungs = [
                _as_float(x, 0.0)
                for x in list(rr_map.get(symbol) or [])
                if _as_float(x, 0.0) > 0.0
            ]
            if round(rung, 6) not in {round(x, 6) for x in rungs}:
                rungs.append(float(rung))
            rr_map[symbol] = sorted(rungs)
            ps["risk_reward_take_profit_taken_rungs_by_symbol"] = rr_map


def _extract_broker_code(ex: dict) -> str:
    payload = ex.get("payload") if isinstance(ex.get("payload"), dict) else {}
    code = payload.get("broker_code")
    if code is not None and str(code).strip():
        return str(code).strip()
    reason = str(ex.get("reason") or "")
    m = re.search(r"broker_rejected:([-\d]+)", reason)
    if m:
        return str(m.group(1)).strip()
    return ""


def _extract_broker_message(ex: dict) -> str:
    payload = ex.get("payload") if isinstance(ex.get("payload"), dict) else {}
    response_payload = payload.get("response_payload") if isinstance(payload.get("response_payload"), dict) else {}
    candidates = [
        payload.get("broker_message"),
        payload.get("return_msg"),
        response_payload.get("return_msg"),
        response_payload.get("msg"),
        response_payload.get("msg1"),
    ]
    for value in candidates:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _is_mock_broker_restricted_symbol_rejection(ex: dict) -> bool:
    if not _is_kiwoom_mock_mode():
        return False
    if _extract_trade_side(ex) != "BUY":
        return False
    code = _extract_broker_code(ex)
    if code != "20":
        return False
    message = _extract_broker_message(ex)
    lowered = message.lower()
    return ("rc4007" in lowered) or ("모의투자 매매제한 종목" in message)


def _update_mock_broker_restricted_symbols(ps: dict, ex: dict) -> None:
    today = _current_session_date()
    records = _normalize_mock_broker_restricted_symbols(ps.get("mock_broker_restricted_symbols"), active_date=today)
    order = ex.get("order") if isinstance(ex.get("order"), dict) else {}
    symbol = normalize_symbol(order.get("symbol") or order.get("stk_cd"))

    if symbol and _is_mock_broker_restricted_symbol_rejection(ex):
        records[symbol] = {
            "symbol": symbol,
            "broker_code": _extract_broker_code(ex),
            "broker_message": _extract_broker_message(ex),
            "reason": str(ex.get("reason") or "").strip(),
            "detected_epoch": _as_int(time.time(), 0),
            "detected_date": today,
        }
    elif symbol and _resolve_execution_ok(ex) and _extract_trade_side(ex) == "BUY":
        records.pop(symbol, None)

    if records:
        ps["mock_broker_restricted_symbols"] = records
    else:
        ps.pop("mock_broker_restricted_symbols", None)


def _reconcile_mock_sell_reject_no_position(ps: dict, ex: dict) -> bool:
    """When broker rejects SELL with no-position code, drop stale local mock position."""
    side = _extract_trade_side(ex)
    if side != "SELL":
        return False

    code = _extract_broker_code(ex)
    if code not in ("20",):
        return False

    order = ex.get("order") if isinstance(ex.get("order"), dict) else {}
    symbol = normalize_symbol(order.get("symbol"))
    if not symbol:
        return False
    req_qty = max(0, _as_int(order.get("qty"), 0))

    pos = _normalize_mock_positions(ps.get("mock_positions"))
    by_symbol = {str(r.get("symbol")): dict(r) for r in pos if isinstance(r, dict)}
    peak_map = _normalize_position_peak_price(ps.get("position_peak_price"), by_symbol.keys())
    strategy_context_map = _normalize_position_strategy_context(ps.get("position_strategy_context"), by_symbol.keys())
    cur = dict(by_symbol.get(symbol) or {})
    cur_qty = max(0, _as_int(cur.get("qty"), 0))
    if cur_qty <= 0:
        return False

    if req_qty <= 0 or req_qty >= cur_qty:
        by_symbol.pop(symbol, None)
        peak_map.pop(symbol, None)
        strategy_context_map.pop(symbol, None)
    else:
        cur["qty"] = int(cur_qty - req_qty)
        by_symbol[symbol] = cur

    final_positions = [v for v in by_symbol.values() if _as_int(v.get("qty"), 0) > 0]
    ps["mock_positions"] = final_positions
    ps["open_positions"] = len(final_positions)
    final_peak_map = _normalize_position_peak_price(peak_map, [row.get("symbol") for row in final_positions])
    if final_peak_map:
        ps["position_peak_price"] = final_peak_map
    else:
        ps.pop("position_peak_price", None)
    final_strategy_context_map = _normalize_position_strategy_context(
        strategy_context_map,
        [row.get("symbol") for row in final_positions],
    )
    if final_strategy_context_map:
        ps["position_strategy_context"] = final_strategy_context_map
    else:
        ps.pop("position_strategy_context", None)
    ps["mock_position_desync_reconciled"] = True
    return True


def _extract_strategist_output_snapshot(state: dict | None) -> dict:
    if not isinstance(state, dict):
        return {}
    strategist_output = state.get("strategist_output") if isinstance(state.get("strategist_output"), dict) else {}
    if strategist_output:
        return dict(strategist_output)
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    cached = persisted.get("strategist_output_cache") if isinstance(persisted.get("strategist_output_cache"), dict) else {}
    output = cached.get("output") if isinstance(cached.get("output"), dict) else {}
    return dict(output) if output else {}


def _extract_order_strategy_snapshot(order: dict | None) -> dict:
    if not isinstance(order, dict):
        return {}
    meta = order.get("meta") if isinstance(order.get("meta"), dict) else {}
    snapshot = (
        meta.get("position_strategy_snapshot")
        if isinstance(meta.get("position_strategy_snapshot"), dict)
        else {}
    )
    return dict(snapshot) if snapshot else {}


def _extract_strategy_policy_snapshot(state: dict | None) -> dict:
    strategist_output = _extract_strategist_output_snapshot(state)
    strategy_policy = strategist_output.get("strategy_policy") if isinstance(strategist_output.get("strategy_policy"), dict) else {}
    if strategy_policy:
        return dict(strategy_policy)
    if isinstance(state, dict):
        if isinstance(state.get("strategy_policy"), dict):
            return dict(state.get("strategy_policy") or {})
        strategist_plan = state.get("strategist_plan") if isinstance(state.get("strategist_plan"), dict) else {}
        if strategist_plan:
            return {"strategist_plan": dict(strategist_plan)}
    return {}


def _remember_recent_monitor_block(ps: dict, state: dict, *, now_epoch: int) -> None:
    monitor_output = state.get("monitor_output") if isinstance(state.get("monitor_output"), dict) else {}
    if not monitor_output:
        return
    action = str(monitor_output.get("action") or "").strip().upper()
    if action in {"BUY", "SELL"}:
        return
    reason = str(
        monitor_output.get("primary_reason_code")
        or monitor_output.get("monitor_reason")
        or monitor_output.get("entry_exit_reason")
        or monitor_output.get("reason")
        or ""
    ).strip()
    symbol = normalize_symbol(
        monitor_output.get("selected_symbol")
        or ((state.get("selected") or {}).get("symbol") if isinstance(state.get("selected"), dict) else "")
    )
    if not symbol or not reason:
        return
    if reason in {"hold", "no_position", "confirmed_exit_signal", "entry_signal_confirmed"}:
        return
    rows = ps.get("recent_monitor_blocks")
    history = [dict(row) for row in rows] if isinstance(rows, list) else []
    history.append({"symbol": symbol, "reason": reason, "epoch": int(now_epoch)})
    history = [row for row in history if isinstance(row, dict) and normalize_symbol(row.get("symbol")) and str(row.get("reason") or "").strip()]
    history = history[-40:]
    ps["recent_monitor_blocks"] = history


def _build_reasoning_trace_snapshot(state: dict) -> dict:
    commander_decision = state.get("commander_decision") if isinstance(state.get("commander_decision"), dict) else {}
    strategy_policy = _extract_strategy_policy_snapshot(state)
    strategist_plan = strategy_policy.get("strategist_plan") if isinstance(strategy_policy.get("strategist_plan"), dict) else {}
    strategist_output = _extract_strategist_output_snapshot(state)
    scanner_output = state.get("scanner_output") if isinstance(state.get("scanner_output"), dict) else {}
    scanner_selection = (
        state.get("scanner_candidate_selection_reason")
        if isinstance(state.get("scanner_candidate_selection_reason"), dict)
        else {}
    )
    monitor_output = state.get("monitor_output") if isinstance(state.get("monitor_output"), dict) else {}
    monitor_action = (
        state.get("monitor_action_decision") if isinstance(state.get("monitor_action_decision"), dict) else {}
    )

    commander_summary = {
        "summary": str(
            commander_decision.get("decision_summary")
            or commander_decision.get("shadow_assessment_summary")
            or ""
        ),
        "command_intent": str(commander_decision.get("command_intent") or ""),
        "strategist_invocation": str(commander_decision.get("strategist_invocation") or ""),
        "llm_policy": str(commander_decision.get("llm_policy") or ""),
        "no_trade_reason_code": str(commander_decision.get("no_trade_reason_code") or ""),
        "source_priority": list(commander_decision.get("source_priority") or []),
        "applied_policy": dict(commander_decision.get("applied_policy") or {}),
        "policy_source": str(commander_decision.get("policy_source") or ""),
        "policy_validation_status": str(commander_decision.get("policy_validation_status") or ""),
        "policy_fallback_used": bool(commander_decision.get("policy_fallback_used")),
        "policy_fallback_reason": str(commander_decision.get("policy_fallback_reason") or ""),
        "policy_partial_normalized": bool(commander_decision.get("policy_partial_normalized")),
        "policy_default_filled_fields": list(commander_decision.get("policy_default_filled_fields") or []),
        "policy_validation_missing_fields": list(commander_decision.get("policy_validation_missing_fields") or []),
        "policy_validation_invalid_fields": list(commander_decision.get("policy_validation_invalid_fields") or []),
        "override_reason": str(commander_decision.get("override_reason") or ""),
        "applied_policy_source_chain": list(commander_decision.get("applied_policy_source_chain") or []),
    }
    strategist_summary = {
        "summary": str(
            strategist_plan.get("strategy_summary")
            or strategist_output.get("strategy_summary")
            or strategist_output.get("summary")
            or ""
        ),
        "selected_playbook": str(
            strategist_plan.get("selected_playbook")
            or strategist_output.get("selected_playbook")
            or strategist_output.get("playbook")
            or ""
        ),
        "candidate_hypotheses": list(strategist_plan.get("candidate_hypotheses") or []),
        "symbol_constraints": dict(strategist_plan.get("symbol_constraints") or {}),
    }
    scanner_summary = {
        "summary": (
            str(scanner_output.get("selection_basis", {}).get("strategy_summary"))
            if isinstance(scanner_output.get("selection_basis"), dict)
            else ""
        )
        or str(
            scanner_selection.get("selection_summary")
            or scanner_output.get("summary")
            or ""
        ),
        "selected_symbol": str(
            scanner_selection.get("selected_symbol")
            or scanner_output.get("selected_symbol")
            or scanner_output.get("top_stock")
            or ""
        ),
        "runner_up_symbol": str(
            scanner_selection.get("runner_up_symbol")
            or scanner_output.get("runner_up_symbol")
            or ""
        ),
        "ranking_factors": list(scanner_output.get("ranking_factors") or []),
        "rejected_candidates": list(scanner_output.get("rejected_candidates") or []),
        "playbook": str(scanner_output.get("playbook") or scanner_output.get("strategist_playbook") or ""),
        "policy_source": str(scanner_output.get("policy_source") or ""),
        "applied_policy_present": bool(scanner_output.get("applied_policy_present")),
        "monitor_entry_policy_summary": dict(scanner_output.get("monitor_entry_policy_summary") or {}),
    }
    monitor_summary = {
        "summary": str(
            monitor_output.get("entry_check_summary")
            or monitor_action.get("entry_check_summary")
            or monitor_output.get("reason")
            or ""
        ),
        "decision": str(monitor_output.get("decision") or monitor_action.get("decision") or ""),
        "action": str(monitor_output.get("action") or monitor_action.get("action") or ""),
        "entry_blockers": list(
            monitor_output.get("entry_blockers") or monitor_action.get("entry_blockers") or []
        ),
        "timing_assessment": dict(
            monitor_output.get("timing_assessment") or monitor_action.get("timing_assessment") or {}
        ),
        "exit_trigger_basis": dict(
            monitor_output.get("exit_trigger_basis") or monitor_action.get("exit_trigger_basis") or {}
        ),
        "received_policy": dict(monitor_output.get("received_policy") or {}),
        "received_policy_source": str(monitor_output.get("received_policy_source") or ""),
        "effective_policy": dict(monitor_output.get("effective_policy") or monitor_output.get("applied_policy") or {}),
        "effective_policy_source": str(monitor_output.get("effective_policy_source") or ""),
        "effective_policy_source_chain": list(monitor_output.get("effective_policy_source_chain") or []),
        "policy_adjustments": dict(monitor_output.get("policy_adjustments") or {}),
        "policy_adjustment_summary": str(monitor_output.get("policy_adjustment_summary") or ""),
        "policy_adjustment_reasoning": str(monitor_output.get("policy_adjustment_reasoning") or ""),
        "effective_policy_deltas": list(monitor_output.get("effective_policy_deltas") or []),
        "applied_policy": dict(monitor_output.get("applied_policy") or {}),
        "policy_source": str(
            monitor_output.get("policy_source")
            or ((monitor_output.get("policy_ref") or {}).get("policy_source") if isinstance(monitor_output.get("policy_ref"), dict) else "")
            or ""
        ),
        "policy_validation_status": str(
            ((monitor_output.get("policy_ref") or {}).get("policy_validation_status") if isinstance(monitor_output.get("policy_ref"), dict) else "")
            or ""
        ),
        "policy_fallback_used": bool(
            ((monitor_output.get("policy_ref") or {}).get("policy_fallback_used") if isinstance(monitor_output.get("policy_ref"), dict) else False)
        ),
        "policy_fallback_reason": str(
            ((monitor_output.get("policy_ref") or {}).get("policy_fallback_reason") if isinstance(monitor_output.get("policy_ref"), dict) else "")
            or ""
        ),
        "policy_partial_normalized": bool(
            ((monitor_output.get("policy_ref") or {}).get("policy_partial_normalized") if isinstance(monitor_output.get("policy_ref"), dict) else False)
        ),
        "policy_default_filled_fields": list(
            ((monitor_output.get("policy_ref") or {}).get("policy_default_filled_fields") if isinstance(monitor_output.get("policy_ref"), dict) else [])
            or []
        ),
        "policy_validation_missing_fields": list(
            ((monitor_output.get("policy_ref") or {}).get("policy_validation_missing_fields") if isinstance(monitor_output.get("policy_ref"), dict) else [])
            or []
        ),
        "policy_validation_invalid_fields": list(
            ((monitor_output.get("policy_ref") or {}).get("policy_validation_invalid_fields") if isinstance(monitor_output.get("policy_ref"), dict) else [])
            or []
        ),
        "override_reason": str(
            ((monitor_output.get("policy_ref") or {}).get("override_reason") if isinstance(monitor_output.get("policy_ref"), dict) else "")
            or ""
        ),
    }
    return build_reasoning_trace_from_summaries(
        commander_summary=commander_summary,
        strategist_summary=strategist_summary,
        scanner_summary=scanner_summary,
        monitor_summary=monitor_summary,
    )


def _build_reasoning_trace_provenance(state: dict) -> dict:
    commander_decision = state.get("commander_decision") if isinstance(state.get("commander_decision"), dict) else {}
    strategy_policy = _extract_strategy_policy_snapshot(state)
    provenance = strategy_policy.get("provenance") if isinstance(strategy_policy.get("provenance"), dict) else {}
    commander_source_refs = commander_decision.get("source_refs") if isinstance(commander_decision.get("source_refs"), dict) else {}

    return build_reasoning_provenance(
        commander_context_source="state.commander_decision",
        strategist_plan_source="state.strategy_policy.strategist_plan"
        if isinstance(strategy_policy.get("strategist_plan"), dict)
        else "state.strategist_output",
        scanner_reason_source="state.scanner_output"
        if isinstance(state.get("scanner_output"), dict)
        else "state.scanner_candidate_selection_reason",
        monitor_reason_source="state.monitor_output"
        if isinstance(state.get("monitor_output"), dict)
        else "state.monitor_action_decision",
        commander_source_ref=str(commander_source_refs.get("shadow_event") or "state.commander_decision"),
        strategist_source_ref="state.strategy_policy.strategist_plan"
        if isinstance(strategy_policy.get("strategist_plan"), dict)
        else "state.strategist_output",
        scanner_source_ref="state.scanner_output"
        if isinstance(state.get("scanner_output"), dict)
        else "state.scanner_candidate_selection_reason",
        monitor_source_ref="state.monitor_output"
        if isinstance(state.get("monitor_output"), dict)
        else "state.monitor_action_decision",
        shadow_used=bool(commander_decision.get("shadow_used") or provenance.get("shadow_used")),
        strategist_fallback_used=bool(
            commander_decision.get("strategist_fallback_used")
            or provenance.get("strategist_fallback_used")
        ),
        source_priority=list(commander_decision.get("source_priority") or []),
    )


def _broker_code_success(value) -> bool | None:  # type: ignore[no-untyped-def]
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return int(float(s)) == 0
    except Exception:
        pass
    t = s.lower()
    if t in ("ok", "success", "accepted"):
        return True
    if t in ("error", "failed", "rejected"):
        return False
    return False


def _resolve_execution_ok(ex: dict) -> bool:
    if "ok" in ex:
        return bool(ex.get("ok", False))

    allowed = bool(ex.get("allowed", False))
    if not allowed:
        return False

    payload = ex.get("payload") if isinstance(ex.get("payload"), dict) else {}
    broker = _broker_code_success(payload.get("broker_code"))
    if broker is not None:
        return bool(broker)

    if "api_ok" in payload:
        return bool(payload.get("api_ok"))

    return allowed


def update_state_after_execution(state: dict) -> dict:
    """M10-3 node: update persisted_state after an execution attempt.

    Inputs:
      - state['execution'] (dict-like), may include:
          - ok: bool
          - blocked: bool
          - reason: str
          - executor: str
          - order: dict
      - state['persisted_state'] (dict)

    Produces:
      - state['persisted_state'] updated:
          - last_order_epoch (only when execution ok == True OR order was actually sent)
          - last_execution_ok
          - last_execution_reason
    """
    ps = state.get("persisted_state") or {}
    ex = state.get("execution") or {}
    ps["mock_positions"] = _normalize_mock_positions(ps.get("mock_positions"))
    ps["open_positions"] = len(ps["mock_positions"])
    ps["position_peak_price"] = _normalize_position_peak_price(
        ps.get("position_peak_price"),
        [row.get("symbol") for row in ps.get("mock_positions") or []],
    )
    if not ps["position_peak_price"]:
        ps.pop("position_peak_price", None)
    ps["position_strategy_context"] = _normalize_position_strategy_context(
        ps.get("position_strategy_context"),
        [row.get("symbol") for row in ps.get("mock_positions") or []],
    )
    if not ps["position_strategy_context"]:
        ps.pop("position_strategy_context", None)
    ps["position_entry_epoch_by_symbol"] = _normalize_position_entry_epoch_map(
        ps.get("position_entry_epoch_by_symbol"),
        [row.get("symbol") for row in ps.get("mock_positions") or []],
    )
    if ps["position_entry_epoch_by_symbol"]:
        for row in ps.get("mock_positions") or []:
            symbol = normalize_symbol(row.get("symbol"))
            entry_epoch = _as_int(ps["position_entry_epoch_by_symbol"].get(symbol), 0)
            if entry_epoch > 0:
                row["position_entry_epoch"] = int(entry_epoch)
    else:
        ps.pop("position_entry_epoch_by_symbol", None)
    last_trade_symbol = normalize_symbol(ps.get("last_trade_symbol"))
    if last_trade_symbol:
        ps["last_trade_symbol"] = last_trade_symbol
    else:
        ps.pop("last_trade_symbol", None)

    # Backward/forward compatible success shape with broker-level override:
    # - execution["ok"] when present
    # - else infer from allowed + payload(broker_code/api_ok)
    ok = _resolve_execution_ok(ex)

    if "blocked" in ex:
        blocked = bool(ex.get("blocked", False))
    else:
        blocked = not bool(ex.get("allowed", False))

    # update audit info always
    ps["last_execution_ok"] = ok
    ps["last_execution_reason"] = ex.get("reason") or ex.get("error") or ("blocked" if blocked else "")
    # Phase 1 Step 5B: additive, observation-only. Does not change order_sent/
    # fill/position bookkeeping below -- `ok` semantics and all existing
    # branches are unchanged. Lets an operator see, from persisted_state
    # alone, whether the last execution's `not ok` was a firm reject/not-sent
    # or an unresolved UNKNOWN awaiting reconciliation.
    ps["last_execution_broker_outcome"] = str(ex.get("broker_outcome") or "")
    ps["last_execution_reconciliation_required"] = bool(ex.get("reconciliation_required"))
    _update_mock_broker_restricted_symbols(ps, ex)

    # Only set last_order_epoch when an order was actually sent.
    # Convention:
    # - In dry-run/mock mode, execution should NOT be treated as "order sent"
    # - In real mode, success implies it was sent
    payload = ex.get("payload") if isinstance(ex.get("payload"), dict) else {}
    mode = str(payload.get("mode") or "").strip().lower()
    is_dry = bool(ex.get("dry_run", False)) or (mode == "mock")
    order_sent = ok and not is_dry

    now_epoch = int(time.time())

    if order_sent:
        ps["last_order_epoch"] = now_epoch

    # Keep recent side/epoch for runtime cooldown and replay guards.
    fill_snapshot = _execution_fill_quantity_snapshot(ex)
    side = _extract_trade_side(ex)
    pending_unfilled = bool(fill_snapshot.get("pending_unfilled")) or _is_zero_fill_truth_pending(fill_snapshot, side)
    if ok and pending_unfilled:
        order = ex.get("order") if isinstance(ex.get("order"), dict) else {}
        _remember_pending_unfilled_order(ps, ex, order, fill_snapshot, now_epoch=now_epoch)

    if ok and not pending_unfilled:
        if side:
            ps["last_trade_side"] = side
            ps["last_trade_epoch"] = now_epoch
            order = ex.get("order") if isinstance(ex.get("order"), dict) else {}
            trade_symbol = normalize_symbol(order.get("symbol") or order.get("stk_cd"))
            if trade_symbol:
                ps["last_trade_symbol"] = trade_symbol
            _remember_post_exit_shadow_watch(ps, ex, state, now_epoch=now_epoch)
            _remember_profit_take_progress(ps, ex, now_epoch=now_epoch)
            _remember_position_entry_risk_progress(ps, ex, now_epoch=now_epoch)
            record_same_symbol_exit(ps, ex, now_epoch=now_epoch)

    # Keep local mock ledger in sync when execution is explicitly mock, or when
    # runtime uses real executor against Kiwoom mock host (KIWOOM_MODE=mock).
    if ok and (mode == "mock" or _is_kiwoom_mock_mode()):
        _apply_mock_fill(ps, ex, state)
    elif not ok and _is_kiwoom_mock_mode():
        _reconcile_mock_sell_reject_no_position(ps, ex)
    _sanitize_closeout_unresolved_flatten_state(ps)

    if not order_sent:
        _remember_recent_monitor_block(ps, state, now_epoch=now_epoch)

    # Canonical reasoning snapshot for downstream reporting/trace consumers.
    # `state["reasoning_trace"]` is the live-cycle source-of-truth and
    # `persisted_state["latest_reasoning_trace"]` is the compatibility mirror.
    reasoning_trace = _build_reasoning_trace_snapshot(state)
    reasoning_trace_provenance = _build_reasoning_trace_provenance(state)
    state["reasoning_trace"] = reasoning_trace
    state["reasoning_trace_provenance"] = reasoning_trace_provenance
    ps["latest_reasoning_trace"] = dict(reasoning_trace)
    ps["latest_reasoning_trace_provenance"] = dict(reasoning_trace_provenance)

    state["persisted_state"] = ps
    return state
