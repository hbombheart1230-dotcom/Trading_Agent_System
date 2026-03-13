from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Dict, Optional
from uuid import uuid4

from libs.read.portfolio_reader import MockPortfolioReader
from libs.read.price_reader import MockPriceReader
from libs.runtime.market_hours import now_kst


NodeFn = Callable[[Dict[str, Any]], Dict[str, Any]]


def _to_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clear_transient_state(state: Dict[str, Any]) -> None:
    for key in (
        "run_id",
        "decision_packet",
        "decision_trace",
        "execution",
        "intents",
        "monitor",
        "monitor_output",
        "monitor_exit",
        "selected",
        "scan_results",
        "ranked_candidates",
        "scanner_output",
        "risk",
        "top_stock",
    ):
        state.pop(key, None)


def _mock_positions_from_state(state: Dict[str, Any]) -> list[dict]:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    rows = persisted.get("mock_positions")
    if not isinstance(rows, list):
        return []
    out: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        qty = _to_int(row.get("qty"), 0)
        if not symbol or qty <= 0:
            continue
        out.append(
            {
                "symbol": symbol,
                "qty": qty,
                "avg_price": _to_float(row.get("avg_price"), 0.0),
                "unrealized_pnl": _to_float(row.get("unrealized_pnl"), 0.0),
            }
        )
    return out


def _mock_cash_from_state(state: Dict[str, Any]) -> float:
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    cash = _to_float(persisted.get("mock_cash"), 0.0)
    if cash > 0.0:
        return float(cash)
    portfolio = state.get("portfolio_snapshot") if isinstance(state.get("portfolio_snapshot"), dict) else {}
    cash = _to_float(portfolio.get("cash"), 0.0)
    if cash > 0.0:
        return float(cash)
    return 2_000_000.0


def _mock_price_from_state(state: Dict[str, Any], symbol: str) -> float:
    market = state.get("market_snapshot") if isinstance(state.get("market_snapshot"), dict) else {}
    if str(market.get("symbol") or "").strip().upper() == symbol:
        px = _to_float(market.get("price"), 0.0)
        if px > 0.0:
            return float(px)
    persisted = state.get("persisted_state") if isinstance(state.get("persisted_state"), dict) else {}
    px = _to_float(persisted.get("last_market_price"), 0.0)
    if px > 0.0:
        return float(px)
    positions = _mock_positions_from_state(state)
    for row in positions:
        if str(row.get("symbol") or "").strip().upper() != symbol:
            continue
        avg = _to_float(row.get("avg_price"), 0.0)
        if avg > 0.0:
            return float(avg)
    return 70_000.0


def _build_mock_portfolio_reader(state: Dict[str, Any]) -> MockPortfolioReader:
    return MockPortfolioReader(
        cash=_mock_cash_from_state(state),
        positions=_mock_positions_from_state(state),
    )


def _build_mock_price_reader(state: Dict[str, Any], symbol: str) -> MockPriceReader:
    px = _mock_price_from_state(state, symbol)
    return MockPriceReader(prices={symbol: px}, default_price=px)


def _intent_from_monitor_state(state: Dict[str, Any]) -> Dict[str, Any]:
    intents = state.get("intents")
    if not isinstance(intents, list) or not intents:
        return {"action": "NOOP", "reason": "no_monitor_intent"}

    it0 = intents[0] if isinstance(intents[0], dict) else {}
    side = str(it0.get("side") or "BUY").strip().upper()
    action = "BUY" if side == "BUY" else "SELL" if side == "SELL" else "NOOP"
    symbol = str(it0.get("symbol") or state.get("symbol") or state.get("selected_symbol") or "").strip().upper()
    qty = max(0, _to_int(it0.get("qty"), 0))

    market = state.get("market_snapshot") if isinstance(state.get("market_snapshot"), dict) else {}
    price = it0.get("price")
    if price is None:
        price = market.get("price")

    return {
        "action": action,
        "symbol": symbol,
        "qty": qty,
        "price": price,
        "order_type": "limit",
        "order_api_id": "ORDER_SUBMIT",
        "rationale": str(it0.get("thesis") or "monitor_intent"),
    }


def _build_packet_from_state(state: Dict[str, Any], *, intent: Dict[str, Any]) -> Dict[str, Any]:
    risk = state.get("risk_context") if isinstance(state.get("risk_context"), dict) else {}
    exec_context = state.get("exec_context") if isinstance(state.get("exec_context"), dict) else {}
    return {
        "intent": dict(intent),
        "risk": dict(risk),
        "exec_context": dict(exec_context),
    }


def run_offhours_validation_once(
    state: Dict[str, Any],
    *,
    dt: Optional[datetime] = None,
    load_state_fn: Optional[NodeFn] = None,
    save_state_fn: Optional[NodeFn] = None,
    build_portfolio_snapshot_fn: Optional[NodeFn] = None,
    build_risk_context_fn: Optional[NodeFn] = None,
    strategist_fn: Optional[NodeFn] = None,
    scanner_fn: Optional[NodeFn] = None,
    build_market_snapshot_fn: Optional[NodeFn] = None,
    monitor_fn: Optional[NodeFn] = None,
    decision_fn: Optional[NodeFn] = None,
    execute_fn: Optional[NodeFn] = None,
    update_state_fn: Optional[NodeFn] = None,
) -> Dict[str, Any]:
    if load_state_fn is None:
        from graphs.nodes.load_state import load_state as load_state_fn
    if save_state_fn is None:
        from graphs.nodes.save_state import save_state as save_state_fn
    if build_portfolio_snapshot_fn is None:
        from graphs.nodes.build_portfolio_snapshot import build_portfolio_snapshot as build_portfolio_snapshot_fn
    if build_risk_context_fn is None:
        from graphs.nodes.build_risk_context import build_risk_context as build_risk_context_fn
    if strategist_fn is None:
        from graphs.nodes.strategist_node import strategist_node as strategist_fn
    if scanner_fn is None:
        from graphs.nodes.scanner_node import scanner_node as scanner_fn
    if build_market_snapshot_fn is None:
        from graphs.nodes.build_market_snapshot import build_market_snapshot as build_market_snapshot_fn
    if monitor_fn is None:
        from graphs.nodes.monitor_node import monitor_node as monitor_fn
    if decision_fn is None:
        from graphs.nodes.decision_node import decision_node as decision_fn
    if execute_fn is None:
        from graphs.nodes.execute_from_packet import execute_from_packet as execute_fn
    if update_state_fn is None:
        from graphs.nodes.update_state_after_execution import update_state_after_execution as update_state_fn

    state = load_state_fn(state)
    _clear_transient_state(state)
    state["run_id"] = str(uuid4().hex)

    tick_dt = dt or now_kst()
    state["tick_ts"] = int(tick_dt.timestamp())
    state["offhours_validation"] = True
    state["path"] = "offhours_validation"
    state["runtime_mode"] = "offhours_validation"

    exec_context = state.get("exec_context") if isinstance(state.get("exec_context"), dict) else {}
    exec_context = dict(exec_context)
    exec_context["mode"] = "mock"
    exec_context["offhours_validation"] = True
    state["exec_context"] = exec_context

    state["portfolio_reader"] = _build_mock_portfolio_reader(state)
    state = build_portfolio_snapshot_fn(state)
    snapshots = state.get("snapshots") if isinstance(state.get("snapshots"), dict) else {}
    state["snapshots"] = {**dict(snapshots or {}), "portfolio": state.get("portfolio_snapshot")}
    state = build_risk_context_fn(state)
    state = strategist_fn(state)
    state = scanner_fn(state)

    selected = state.get("selected") if isinstance(state.get("selected"), dict) else {}
    symbol = str(selected.get("symbol") or state.get("symbol") or "").strip().upper()
    if symbol:
        state["symbol"] = symbol
        state["price_reader"] = _build_mock_price_reader(state, symbol)
        state = build_market_snapshot_fn(state)

    state = monitor_fn(state)
    state = decision_fn(state)

    if str(state.get("decision") or "").strip().lower() == "approve":
        intent = _intent_from_monitor_state(state)
        state["decision_packet"] = _build_packet_from_state(state, intent=intent)
        state = execute_fn(state)
        state = update_state_fn(state)

    state = save_state_fn(state)
    return state
