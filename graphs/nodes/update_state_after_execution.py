from __future__ import annotations

import os
import time


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


def _normalize_mock_positions(raw):  # type: ignore[no-untyped-def]
    out = []
    if not isinstance(raw, list):
        return out
    for row in raw:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip()
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
    return out


def _default_mock_cash() -> float:
    raw = str(os.getenv("MOCK_CASH_FALLBACK", "2000000") or "2000000").strip()
    v = _as_float(raw, 2000000.0)
    return v if v > 0.0 else 2000000.0


def _ensure_mock_cash(ps: dict) -> float:
    cur = _as_float(ps.get("mock_cash"), 0.0)
    if cur > 0.0:
        return cur
    base = _default_mock_cash()
    ps["mock_cash"] = float(base)
    return float(base)


def _apply_mock_fill(ps: dict, ex: dict) -> None:
    order = ex.get("order") if isinstance(ex.get("order"), dict) else {}
    action = str(order.get("action") or "").strip().upper()
    symbol = str(order.get("symbol") or "").strip()
    qty = _as_int(order.get("qty"), 0)
    price = _as_float(order.get("price"), 0.0)
    if action not in ("BUY", "SELL") or not symbol or qty <= 0:
        return

    pos = _normalize_mock_positions(ps.get("mock_positions"))
    by_symbol = {str(r.get("symbol")): dict(r) for r in pos if isinstance(r, dict)}
    cur = dict(by_symbol.get(symbol) or {"symbol": symbol, "qty": 0, "avg_price": 0.0, "unrealized_pnl": 0.0})
    cash = _ensure_mock_cash(ps)
    realized_total = _as_float(ps.get("mock_realized_pnl"), 0.0)

    if action == "BUY":
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
    else:
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
        else:
            cur["qty"] = new_qty
            by_symbol[symbol] = cur

    final_positions = [v for v in by_symbol.values() if _as_int(v.get("qty"), 0) > 0]
    ps["mock_positions"] = final_positions
    ps["open_positions"] = len(final_positions)
    ps["mock_cash"] = float(cash)
    ps["mock_realized_pnl"] = float(realized_total)


def _extract_trade_side(ex: dict) -> str:
    order = ex.get("order") if isinstance(ex.get("order"), dict) else {}
    side = str(order.get("action") or "").strip().upper()
    if side in ("BUY", "SELL"):
        return side
    return ""


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

    # Backward/forward compatible success shape:
    # - legacy: execution["ok"]
    # - current: execution["allowed"]
    if "ok" in ex:
        ok = bool(ex.get("ok", False))
    else:
        ok = bool(ex.get("allowed", False))

    if "blocked" in ex:
        blocked = bool(ex.get("blocked", False))
    else:
        blocked = not bool(ex.get("allowed", False))

    # update audit info always
    ps["last_execution_ok"] = ok
    ps["last_execution_reason"] = ex.get("reason") or ex.get("error") or ("blocked" if blocked else "")

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
    if ok:
        side = _extract_trade_side(ex)
        if side:
            ps["last_trade_side"] = side
            ps["last_trade_epoch"] = now_epoch

    # Keep mock portfolio position state in sync with successful mock executions.
    if ok and mode == "mock":
        _apply_mock_fill(ps, ex)

    state["persisted_state"] = ps
    return state
