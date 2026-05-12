from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, Optional, Tuple

from libs.core.symbols import is_valid_symbol, normalize_symbol
from libs.runtime.canonical_artifacts import write_executor_artifact, write_supervisor_artifact
from libs.runtime.asset_universe_policy import inspect_asset_universe_candidate
from libs.runtime.decision_trace import append_decision_trace


def _import_api_catalog():
    from libs.catalog.api_catalog import ApiCatalog  # type: ignore
    return ApiCatalog


def _import_request_builder():
    from libs.catalog.api_request_builder import ApiRequestBuilder  # type: ignore
    return ApiRequestBuilder


def _import_settings():
    from libs.core.settings import Settings  # type: ignore
    return Settings


def _import_event_logger():
    """Try multiple locations for EventLogger/new_run_id."""
    for mod in (
        "libs.event_logger",
        "libs.logging.event_logger",
        "libs.core.event_logger",
    ):
        try:
            m = __import__(mod, fromlist=["EventLogger", "new_run_id"])
            return getattr(m, "EventLogger"), getattr(m, "new_run_id")
        except Exception:
            continue
    # final fallback: local minimal logger
    from libs.core.event_logger import EventLogger, new_run_id  # type: ignore
    return EventLogger, new_run_id


def _import_supervisor():
    from libs.risk.supervisor import Supervisor  # type: ignore
    return Supervisor


def _import_get_executor():
    # returns get_executor() factory
    try:
        from libs.execution.executors import get_executor  # type: ignore
        return get_executor
    except Exception:
        from libs.execution.executors.factory import get_executor  # type: ignore
        return get_executor


def _catalog_path_from_env() -> str:
    # New canonical key
    p = os.getenv("KIWOOM_API_CATALOG_PATH")
    if p:
        return p
    # Legacy keys (kept for backwards compatibility)
    for k in ("KIWOOM_REGISTRY_APIS_JSONL", "KIWOOM_REGISTRY_TAGGED_JSONL"):
        v = os.getenv(k)
        if v:
            return v
    return "./data/specs/api_catalog.jsonl"


def _resolve_execution_mode() -> str:
    """Resolve effective execution mode consistently with executor factory."""
    mode = (os.getenv("EXECUTION_MODE", "") or "").strip().lower()
    if mode in ("mock", "real"):
        return mode

    try:
        Settings = _import_settings()
        s = Settings.from_env()
        base = str(getattr(s, "kiwoom_mode", "mock") or "mock").strip().lower()
        return "real" if base == "real" else "mock"
    except Exception:
        return "mock"


def _is_kiwoom_mock_mode() -> bool:
    return str(os.getenv("KIWOOM_MODE", "mock") or "mock").strip().lower() == "mock"


def _is_kiwoom_mock_broker_http_mode() -> bool:
    # Kiwoom mock REST path: KIWOOM_MODE=mock with EXECUTION_MODE=real.
    return _is_kiwoom_mock_mode() and _resolve_execution_mode() == "real"


def _execution_mode_details() -> Dict[str, str]:
    execution_mode = _resolve_execution_mode()
    kiwoom_mode = "mock" if _is_kiwoom_mock_mode() else "real"
    broker_env = "mock" if kiwoom_mode == "mock" else "real"
    if execution_mode == "mock":
        effective_mode = "mock_executor"
    elif kiwoom_mode == "mock":
        effective_mode = "mock_broker_http"
    else:
        effective_mode = "real_broker_http"
    return {
        "execution_mode": str(execution_mode),
        "kiwoom_mode": str(kiwoom_mode),
        "broker_env": str(broker_env),
        "effective_mode": str(effective_mode),
    }


def _is_trueish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _parse_symbol_allowlist(raw: Optional[str]) -> set[str]:
    if raw is None:
        return set()
    v = raw.strip()
    if not v:
        return set()
    return {normalize_symbol(x) for x in v.split(",") if normalize_symbol(x)}


def _resolve_limit_env_value(primary: str, alias: str) -> Tuple[int, str]:
    v = _coerce_int(os.getenv(primary), 0)
    if v > 0:
        return int(v), str(primary)
    alt = _coerce_int(os.getenv(alias), 0)
    if alt > 0:
        return int(alt), str(alias)
    return 0, str(primary)


def _evaluate_symbol_allowlist_guard(order: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    action = str(order.get("action") or "").strip().upper()
    if action not in ("BUY", "SELL"):
        return True, "", {"enabled": False, "guard_applied": False, "action": action}

    allow = _parse_symbol_allowlist(os.getenv("SYMBOL_ALLOWLIST"))
    symbol = _extract_order_symbol(order)
    details: Dict[str, Any] = {
        "enabled": bool(allow),
        "guard_applied": True,
        "action": action,
        "symbol": symbol,
        "allowlist_size": len(allow),
    }
    if not allow:
        return True, "", details
    if not symbol:
        details["symbol_evaluable"] = False
        return True, "", details
    if symbol and symbol in allow:
        return True, "", details
    details["allowlist"] = sorted(allow)
    return False, "symbol_not_allowlisted", details


def _extract_market_quotes_safe(state: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    try:
        from graphs.nodes.skill_contracts import extract_market_quotes  # type: ignore

        quotes, _meta = extract_market_quotes(state)
        return dict(quotes or {})
    except Exception:
        return {}


def _evaluate_asset_universe_guard(state: Dict[str, Any], order: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    action = str(order.get("action") or "").strip().upper()
    details: Dict[str, Any] = {
        "guard_applied": True,
        "action": action,
    }
    if action != "BUY":
        details["risk_reducing"] = action in ("SELL", "EXIT", "CLOSE")
        return True, "", details

    symbol = _extract_order_symbol(order)
    details["symbol"] = symbol
    if not symbol:
        details["symbol_evaluable"] = False
        return True, "", details

    inspection = inspect_asset_universe_candidate(
        symbol=symbol,
        candidate=state.get("selected") if isinstance(state.get("selected"), dict) else None,
        state=state,
        policy=state.get("policy") if isinstance(state.get("policy"), dict) else {},
        market_quotes=_extract_market_quotes_safe(state),
        allow_remote_lookup=True,
    )
    details.update(
        {
            "asset_policy_type": str(inspection.get("asset_policy_type") or ""),
            "asset_policy_source": str(inspection.get("asset_policy_source") or ""),
            "asset_class_detected": str(inspection.get("asset_class_detected") or ""),
            "detection_source": str(inspection.get("detection_source") or ""),
            "detection_field": str(inspection.get("detection_field") or ""),
            "excluded_by_asset_policy": bool(inspection.get("excluded_by_asset_policy")),
            "exclusion_reason": str(inspection.get("exclusion_reason") or ""),
            "detected_name": str(inspection.get("detected_name") or ""),
        }
    )
    if bool(inspection.get("excluded_by_asset_policy")):
        return False, "asset_universe_policy_blocked", details
    return True, "", details


def _evaluate_symbol_format_guard(order: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    action = str(order.get("action") or "").strip().upper()
    if action not in ("BUY", "SELL"):
        return True, "", {"guard_applied": False, "action": action}

    raw_symbol = order.get("symbol_raw") or order.get("symbol") or order.get("stk_cd")
    symbol = normalize_symbol(raw_symbol)
    details: Dict[str, Any] = {
        "guard_applied": True,
        "action": action,
        "raw_symbol": str(raw_symbol or "").strip(),
        "symbol": symbol,
    }
    if not is_valid_symbol(raw_symbol):
        return False, "invalid_symbol_format", details
    return True, "", details


def _evaluate_order_limit_guard(state: Dict[str, Any], order: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    action = str(order.get("action") or "").strip().upper()
    if action not in ("BUY", "SELL"):
        return True, "", {"guard_applied": False, "action": action}
    if action == "SELL":
        return True, "", {"guard_applied": True, "action": action, "risk_reducing": True}

    qty = _coerce_int(order.get("qty"), 0)
    max_qty, qty_key = _resolve_limit_env_value("MAX_ORDER_QTY", "MAX_QTY")
    max_notional, notional_key = _resolve_limit_env_value("MAX_ORDER_NOTIONAL", "MAX_NOTIONAL")
    price, price_source = _resolve_order_price_for_notional_with_source(state, order)

    details: Dict[str, Any] = {
        "guard_applied": True,
        "action": action,
        "qty": int(qty),
        "price": float(price) if price is not None else None,
        "price_source": str(price_source),
        "max_qty_key": str(qty_key),
        "max_qty": int(max_qty),
        "max_notional_key": str(notional_key),
        "max_notional": int(max_notional),
    }

    if max_qty > 0 and qty > max_qty:
        details["limit_exceeded"] = "qty"
        return False, "order_qty_limit_exceeded", details

    if max_notional > 0 and qty > 0 and price <= 0:
        details["price_evaluable"] = False
        details["limit_exceeded"] = "notional_price_missing"
        return False, "order_notional_price_missing", details

    if max_notional > 0 and qty > 0 and price > 0:
        notional = float(qty) * float(price)
        details["order_notional"] = float(notional)
        if notional > float(max_notional):
            details["limit_exceeded"] = "notional"
            return False, "order_notional_limit_exceeded", details

    return True, "", details


def _extract_upper_limit_quote_snapshot(state: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "symbol": normalize_symbol(symbol),
        "quote_present": False,
        "source": "",
        "current_price": 0.0,
        "upper_limit_price": 0.0,
        "best_ask": 0.0,
        "best_bid": 0.0,
        "change_pct": 0.0,
        "raw_row_present": False,
    }
    if not out["symbol"]:
        return out

    quote: Dict[str, Any] = {}
    try:
        from graphs.nodes.skill_contracts import extract_market_quotes  # type: ignore

        quotes, _meta = extract_market_quotes(state)
        q = quotes.get(out["symbol"])
        if isinstance(q, dict):
            quote = dict(q)
    except Exception:
        quote = {}

    if not quote:
        return out

    out["quote_present"] = True
    out["source"] = "skill.market.quote"
    out["current_price"] = _coerce_float(quote.get("price") or quote.get("cur"), 0.0)
    out["best_ask"] = _coerce_float(quote.get("best_ask") or quote.get("ask"), 0.0)
    out["best_bid"] = _coerce_float(quote.get("best_bid") or quote.get("bid"), 0.0)
    out["change_pct"] = _coerce_float(quote.get("change_pct"), 0.0)

    raw_quote = quote.get("raw") if isinstance(quote.get("raw"), dict) else {}
    raw_rows = raw_quote.get("cntr_infr") if isinstance(raw_quote.get("cntr_infr"), list) else []
    raw_row = raw_rows[0] if raw_rows and isinstance(raw_rows[0], dict) else {}
    if raw_row:
        out["raw_row_present"] = True
        if out["current_price"] <= 0.0:
            out["current_price"] = _coerce_float(raw_row.get("cur_prc"), 0.0)
        if out["best_ask"] <= 0.0:
            out["best_ask"] = _coerce_float(raw_row.get("pri_sel_bid_unit") or raw_row.get("sel_1bid"), 0.0)
        if out["best_bid"] <= 0.0:
            out["best_bid"] = _coerce_float(raw_row.get("pri_buy_bid_unit") or raw_row.get("buy_1bid"), 0.0)
        if abs(out["change_pct"]) <= 1e-9:
            out["change_pct"] = _coerce_float(raw_row.get("pre_rt") or raw_row.get("flu_rt"), 0.0)
        out["upper_limit_price"] = _coerce_float(
            raw_row.get("upl_pric") or raw_quote.get("upl_pric") or quote.get("upl_pric"),
            0.0,
        )

    for key in ("current_price", "upper_limit_price", "best_ask", "best_bid"):
        out[key] = abs(_coerce_float(out.get(key), 0.0))

    return out


def _augment_quote_snapshot_with_spread(snapshot: Dict[str, Any] | None) -> Dict[str, Any]:
    quote = dict(snapshot or {})
    best_ask = abs(_coerce_float(quote.get("best_ask"), 0.0))
    best_bid = abs(_coerce_float(quote.get("best_bid"), 0.0))
    current_price = abs(_coerce_float(quote.get("current_price"), 0.0))
    quote["best_ask"] = float(best_ask)
    quote["best_bid"] = float(best_bid)
    quote["current_price"] = float(current_price)

    spread_bps = 0.0
    if best_ask > 0.0 and best_bid > 0.0:
        mid = (best_ask + best_bid) / 2.0
        if mid > 0.0:
            spread_bps = ((best_ask - best_bid) / mid) * 10000.0
    quote["spread_bps"] = float(spread_bps) if spread_bps > 0.0 else 0.0
    return quote


def _evaluate_upper_limit_buy_guard(state: Dict[str, Any], order: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    action = str(order.get("action") or "").strip().upper()
    if action != "BUY":
        return True, "", {"guard_applied": False, "action": action}

    symbol = _extract_order_symbol(order)
    details = {
        "guard_applied": True,
        "action": action,
        "symbol": symbol,
        "enabled": True,
    }
    if not symbol:
        details["symbol_evaluable"] = False
        return True, "", details

    quote = _extract_upper_limit_quote_snapshot(state, symbol)
    details["quote"] = quote
    if not bool(quote.get("quote_present")):
        details["quote_evaluable"] = False
        return True, "", details

    current_price = _coerce_float(quote.get("current_price"), 0.0)
    upper_limit_price = _coerce_float(quote.get("upper_limit_price"), 0.0)
    best_ask = _coerce_float(quote.get("best_ask"), 0.0)
    change_pct = _coerce_float(quote.get("change_pct"), 0.0)

    at_upper_limit = upper_limit_price > 0.0 and current_price >= max(0.0, upper_limit_price - 1e-6)
    no_visible_ask = best_ask <= 0.0
    suspicious_limit_up = change_pct >= 29.5 and no_visible_ask
    limit_locked = bool(at_upper_limit and (no_visible_ask or best_ask >= upper_limit_price > 0.0))

    details.update(
        {
            "current_price": float(current_price),
            "upper_limit_price": float(upper_limit_price),
            "best_ask": float(best_ask),
            "change_pct": float(change_pct),
            "at_upper_limit": bool(at_upper_limit),
            "limit_locked": bool(limit_locked),
            "suspicious_limit_up": bool(suspicious_limit_up),
        }
    )

    if at_upper_limit or suspicious_limit_up:
        details["block_reason"] = "price_at_or_near_upper_limit"
        return False, "upper_limit_buy_blocked", details
    return True, "", details


def _should_attempt_upper_limit_cancel(state: Dict[str, Any], execution: Dict[str, Any], order: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
    action = str(order.get("action") or "").strip().upper()
    details: Dict[str, Any] = {"guard_applied": True, "action": action}
    if action != "BUY":
        return False, details
    if _resolve_execution_mode() != "real":
        details["reason"] = "execution_mode_not_real"
        return False, details
    if not bool(execution.get("allowed")) or not bool(execution.get("ok")):
        details["reason"] = "execution_not_accepted"
        return False, details

    order_id = str((((execution.get("payload") or {}) if isinstance(execution.get("payload"), dict) else {}).get("order_id")) or "").strip()
    if not order_id:
        details["reason"] = "missing_order_id"
        return False, details

    allowed, reason, guard_details = _evaluate_upper_limit_buy_guard(state, order)
    details["order_id"] = order_id
    details["upper_limit_guard"] = guard_details
    if allowed:
        details["reason"] = "upper_limit_not_detected"
        return False, details
    details["reason"] = reason or "upper_limit_buy_blocked"
    return True, details


def _attempt_upper_limit_cancel(*, state: Dict[str, Any], catalog: Any, executor: Any, order: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
    attempt, details = _should_attempt_upper_limit_cancel(state, execution, order)
    result: Dict[str, Any] = {"attempted": bool(attempt), **details}
    if not attempt:
        return result

    order_id = str(details.get("order_id") or "").strip()
    symbol = _extract_order_symbol(order)
    cancel_order: Dict[str, Any] = {
        "api_id": "kt10003",
        "action": "CANCEL",
        "symbol": symbol,
        "stk_cd": symbol,
        "orig_ord_no": order_id,
        "cncl_qty": "0",
        "dmst_stex_tp": str(order.get("dmst_stex_tp") or "KRX"),
        "rationale": "upper_limit_buy_auto_cancel",
    }
    try:
        cancel_req = _prepare_request(cancel_order, catalog)
        cancel_execution_result = executor.execute(cancel_req)
        cancel_payload = _normalize_execution(
            allowed=True,
            execution_result=cancel_execution_result,
            allow_result=None,
            order=cancel_order,
            reason="upper_limit_buy_auto_cancel",
            strategy_policy_summary=None,
        )
        result["cancel"] = cancel_payload
        result["cancel_ok"] = bool(cancel_payload.get("ok"))
        return result
    except Exception as exc:
        result["cancel_ok"] = False
        result["cancel_error"] = str(exc)
        return result


def _extract_order_symbol(order: Dict[str, Any]) -> str:
    sym = order.get("symbol") or order.get("stk_cd")
    return normalize_symbol(sym)


def _extract_active_mock_broker_restricted_symbol_record(state: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    sym = normalize_symbol(symbol)
    if not sym:
        return {}
    persisted = state.get("persisted_state")
    if not isinstance(persisted, dict):
        return {}
    records = persisted.get("mock_broker_restricted_symbols")
    if not isinstance(records, dict):
        return {}
    raw = records.get(sym)
    if not isinstance(raw, dict):
        return {}
    today = str(time.strftime("%Y-%m-%d") or "").strip()
    detected_date = str(raw.get("detected_date") or "").strip()
    if detected_date and today and detected_date != today:
        return {}
    row = dict(raw)
    row["symbol"] = sym
    return row


def _evaluate_mock_broker_restricted_symbol_guard(state: Dict[str, Any], order: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    action = str(order.get("action") or "").strip().upper()
    details: Dict[str, Any] = {
        "guard_applied": True,
        "action": action,
        "enabled": True,
        "mock_mode": bool(_is_kiwoom_mock_mode()),
    }
    if action != "BUY":
        return True, "", details
    if not _is_kiwoom_mock_mode():
        return True, "", details

    symbol = _extract_order_symbol(order)
    details["symbol"] = symbol
    if not symbol:
        details["symbol_evaluable"] = False
        return True, "", details

    restriction_record = _extract_active_mock_broker_restricted_symbol_record(state, symbol)
    if not restriction_record:
        details["blocked"] = False
        return True, "", details

    details["blocked"] = True
    details["restriction_record"] = restriction_record
    details["broker_code"] = str(restriction_record.get("broker_code") or "")
    details["broker_message"] = str(restriction_record.get("broker_message") or "")
    details["detected_date"] = str(restriction_record.get("detected_date") or "")
    return False, "mock_broker_restricted_symbol_blocked", details


def _extract_open_symbols_from_state(state: Dict[str, Any]) -> set[str]:
    symbols: set[str] = set()

    port = state.get("portfolio_snapshot")
    if isinstance(port, dict):
        rows = port.get("positions")
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                sym = normalize_symbol(row.get("symbol"))
                qty = _coerce_int(row.get("qty"), 0)
                if sym and qty > 0:
                    symbols.add(sym)

    persisted = state.get("persisted_state")
    if isinstance(persisted, dict):
        rows = persisted.get("mock_positions")
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                sym = normalize_symbol(row.get("symbol"))
                qty = _coerce_int(row.get("qty"), 0)
                if sym and qty > 0:
                    symbols.add(sym)
    return symbols


def _should_block_duplicate_mock_buy(state: Dict[str, Any], order: Dict[str, Any]) -> bool:
    if _resolve_execution_mode() != "mock":
        return False
    action = str(order.get("action") or "").strip().upper()
    if action != "BUY":
        return False
    sym = _extract_order_symbol(order)
    if not sym:
        return False
    return sym in _extract_open_symbols_from_state(state)


_RECENT_BUY_GUARD_DEFAULT_TTL_SEC = 600
_RECENT_BUY_GUARD_DEFAULT_PATH = Path("data/state/execution_recent_buy_guard.json")
_RECENT_SELL_GUARD_DEFAULT_TTL_SEC = 180
_RECENT_SELL_GUARD_DEFAULT_PATH = Path("data/state/execution_recent_sell_guard.json")


def _recent_buy_guard_enabled(state: Dict[str, Any]) -> bool:
    if str(state.get("recent_buy_guard_path") or "").strip():
        return True
    details = _execution_mode_details()
    if str(details.get("effective_mode") or "") not in ("mock_broker_http", "real_broker_http"):
        return False
    return any(str(state.get(key) or "").strip() for key in ("runtime_mode", "runtime_phase", "phase", "tick_ts"))


def _recent_buy_guard_path(state: Dict[str, Any]) -> Path:
    raw = str(state.get("recent_buy_guard_path") or "").strip()
    return Path(raw) if raw else _RECENT_BUY_GUARD_DEFAULT_PATH


def _recent_sell_guard_enabled(state: Dict[str, Any]) -> bool:
    if str(state.get("recent_sell_guard_path") or "").strip():
        return True
    details = _execution_mode_details()
    if str(details.get("effective_mode") or "") not in ("mock_broker_http", "real_broker_http"):
        return False
    return any(str(state.get(key) or "").strip() for key in ("runtime_mode", "runtime_phase", "phase", "tick_ts"))


def _recent_sell_guard_path(state: Dict[str, Any]) -> Path:
    raw = str(state.get("recent_sell_guard_path") or "").strip()
    return Path(raw) if raw else _RECENT_SELL_GUARD_DEFAULT_PATH


def _recent_buy_guard_now_epoch(state: Dict[str, Any]) -> int:
    for key in ("tick_ts", "now_epoch"):
        epoch = _coerce_int(state.get(key), 0)
        if epoch > 0:
            return int(epoch)
    return int(time.time())


def _recent_buy_guard_ttl_sec(state: Dict[str, Any]) -> int:
    raw = state.get("recent_buy_guard_ttl_sec")
    ttl = _coerce_int(raw, _RECENT_BUY_GUARD_DEFAULT_TTL_SEC)
    return int(ttl if ttl > 0 else _RECENT_BUY_GUARD_DEFAULT_TTL_SEC)


def _recent_sell_guard_ttl_sec(state: Dict[str, Any]) -> int:
    raw = state.get("recent_sell_guard_ttl_sec")
    ttl = _coerce_int(raw, _RECENT_SELL_GUARD_DEFAULT_TTL_SEC)
    return int(ttl if ttl > 0 else _RECENT_SELL_GUARD_DEFAULT_TTL_SEC)


def _read_recent_buy_guard(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists():
            return {"schema_version": "execution_recent_buy_guard.v1", "orders": {}}
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            orders = data.get("orders")
            if not isinstance(orders, dict):
                data["orders"] = {}
            return data
    except Exception:
        pass
    return {"schema_version": "execution_recent_buy_guard.v1", "orders": {}}


def _read_recent_sell_guard(path: Path) -> Dict[str, Any]:
    try:
        if not path.exists():
            return {"schema_version": "execution_recent_sell_guard.v1", "orders": {}}
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            orders = data.get("orders")
            if not isinstance(orders, dict):
                data["orders"] = {}
            return data
    except Exception:
        pass
    return {"schema_version": "execution_recent_sell_guard.v1", "orders": {}}


def _write_recent_buy_guard(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _write_recent_sell_guard(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _position_qty_hint_from_order(order: Dict[str, Any]) -> int:
    meta = order.get("meta") if isinstance(order.get("meta"), dict) else {}
    for key in ("position_qty", "available_qty", "sellable_qty", "qty_available"):
        qty = _coerce_int(meta.get(key), 0)
        if qty > 0:
            return int(qty)
    return 0


def _evaluate_recent_buy_order_guard(state: Dict[str, Any], order: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    action = str(order.get("action") or "").strip().upper()
    details: Dict[str, Any] = {
        "enabled": bool(_recent_buy_guard_enabled(state)),
        "action": action,
        "guard_applied": False,
    }
    if action != "BUY" or not details["enabled"]:
        return True, "", details

    symbol = _extract_order_symbol(order)
    details["symbol"] = symbol
    details["guard_applied"] = True
    if not symbol:
        details["symbol_evaluable"] = False
        return True, "", details

    path = _recent_buy_guard_path(state)
    now_epoch = _recent_buy_guard_now_epoch(state)
    ttl_sec = _recent_buy_guard_ttl_sec(state)
    data = _read_recent_buy_guard(path)
    orders = data.get("orders") if isinstance(data.get("orders"), dict) else {}
    record = orders.get(symbol) if isinstance(orders.get(symbol), dict) else {}
    expires_epoch = _coerce_int(record.get("expires_epoch"), 0)
    last_buy_epoch = _coerce_int(record.get("last_buy_epoch"), 0)

    details.update(
        {
            "path": str(path),
            "now_epoch": int(now_epoch),
            "ttl_sec": int(ttl_sec),
            "last_buy_epoch": int(last_buy_epoch),
            "expires_epoch": int(expires_epoch),
            "recent_order_found": bool(record),
        }
    )
    if record and expires_epoch > 0 and now_epoch <= expires_epoch:
        details["remaining_sec"] = int(max(0, expires_epoch - now_epoch))
        details["order_id"] = str(record.get("order_id") or "")
        details["run_id"] = str(record.get("run_id") or "")
        return False, "duplicate_buy_recent_order_exists", details
    return True, "", details


def _evaluate_recent_sell_order_guard(state: Dict[str, Any], order: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    action = str(order.get("action") or "").strip().upper()
    details: Dict[str, Any] = {
        "enabled": bool(_recent_sell_guard_enabled(state)),
        "action": action,
        "guard_applied": False,
    }
    if action != "SELL" or not details["enabled"]:
        return True, "", details

    symbol = _extract_order_symbol(order)
    details["symbol"] = symbol
    details["guard_applied"] = True
    if not symbol:
        details["symbol_evaluable"] = False
        return True, "", details

    path = _recent_sell_guard_path(state)
    now_epoch = _recent_buy_guard_now_epoch(state)
    ttl_sec = _recent_sell_guard_ttl_sec(state)
    data = _read_recent_sell_guard(path)
    orders = data.get("orders") if isinstance(data.get("orders"), dict) else {}
    record = orders.get(symbol) if isinstance(orders.get(symbol), dict) else {}
    expires_epoch = _coerce_int(record.get("expires_epoch"), 0)
    order_qty = _coerce_int(order.get("qty"), 0)
    remaining_qty_hint = _coerce_int(record.get("remaining_qty_hint"), -1)

    details.update(
        {
            "path": str(path),
            "now_epoch": int(now_epoch),
            "ttl_sec": int(ttl_sec),
            "order_qty": int(order_qty),
            "remaining_qty_hint": int(remaining_qty_hint),
            "expires_epoch": int(expires_epoch),
            "recent_order_found": bool(record),
        }
    )
    if not record or expires_epoch <= 0 or now_epoch > expires_epoch:
        return True, "", details
    details["remaining_sec"] = int(max(0, expires_epoch - now_epoch))
    details["last_sell_epoch"] = _coerce_int(record.get("last_sell_epoch"), 0)
    details["last_sell_qty"] = _coerce_int(record.get("last_sell_qty"), 0)
    details["last_position_qty"] = _coerce_int(record.get("position_qty_hint"), 0)
    if remaining_qty_hint <= 0:
        return False, "duplicate_sell_recent_full_exit_exists", details
    if order_qty > 0 and order_qty > remaining_qty_hint:
        return False, "sell_qty_exceeds_recent_remaining_position", details
    return True, "", details


def _update_recent_buy_order_guard(state: Dict[str, Any], order: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
    action = str(order.get("action") or "").strip().upper()
    if action not in ("BUY", "SELL") or not _recent_buy_guard_enabled(state):
        return {"enabled": False, "action": action, "updated": False}
    if not bool(execution.get("execution_ok", execution.get("ok"))):
        return {"enabled": True, "action": action, "updated": False, "reason": "execution_not_ok"}

    symbol = _extract_order_symbol(order)
    if not symbol:
        return {"enabled": True, "action": action, "updated": False, "reason": "symbol_missing"}

    path = _recent_buy_guard_path(state)
    now_epoch = _recent_buy_guard_now_epoch(state)
    ttl_sec = _recent_buy_guard_ttl_sec(state)
    data = _read_recent_buy_guard(path)
    data["schema_version"] = "execution_recent_buy_guard.v1"
    orders = data.get("orders") if isinstance(data.get("orders"), dict) else {}
    data["orders"] = orders

    for sym, record in list(orders.items()):
        if not isinstance(record, dict) or _coerce_int(record.get("expires_epoch"), 0) <= now_epoch:
            orders.pop(sym, None)

    if action == "SELL":
        removed = bool(orders.pop(symbol, None))
        _write_recent_buy_guard(path, data)
        return {
            "enabled": True,
            "action": action,
            "symbol": symbol,
            "updated": bool(removed),
            "cleared": bool(removed),
            "path": str(path),
        }

    payload = execution.get("payload") if isinstance(execution.get("payload"), dict) else {}
    orders[symbol] = {
        "symbol": symbol,
        "last_buy_epoch": int(now_epoch),
        "expires_epoch": int(now_epoch + ttl_sec),
        "ttl_sec": int(ttl_sec),
        "order_id": str(execution.get("order_id") or execution.get("ord_no") or payload.get("order_id") or ""),
        "run_id": str(state.get("run_id") or ""),
        "qty": _coerce_int(order.get("qty"), 0),
        "effective_mode": str(_execution_mode_details().get("effective_mode") or ""),
    }
    _write_recent_buy_guard(path, data)
    return {
        "enabled": True,
        "action": action,
        "symbol": symbol,
        "updated": True,
        "expires_epoch": int(now_epoch + ttl_sec),
        "ttl_sec": int(ttl_sec),
        "path": str(path),
    }


def _update_recent_sell_order_guard(state: Dict[str, Any], order: Dict[str, Any], execution: Dict[str, Any]) -> Dict[str, Any]:
    action = str(order.get("action") or "").strip().upper()
    if action not in ("BUY", "SELL") or not _recent_sell_guard_enabled(state):
        return {"enabled": False, "action": action, "updated": False}
    if not bool(execution.get("execution_ok", execution.get("ok"))):
        return {"enabled": True, "action": action, "updated": False, "reason": "execution_not_ok"}

    symbol = _extract_order_symbol(order)
    if not symbol:
        return {"enabled": True, "action": action, "updated": False, "reason": "symbol_missing"}

    path = _recent_sell_guard_path(state)
    now_epoch = _recent_buy_guard_now_epoch(state)
    ttl_sec = _recent_sell_guard_ttl_sec(state)
    data = _read_recent_sell_guard(path)
    data["schema_version"] = "execution_recent_sell_guard.v1"
    orders = data.get("orders") if isinstance(data.get("orders"), dict) else {}
    data["orders"] = orders

    for sym, record in list(orders.items()):
        if not isinstance(record, dict) or _coerce_int(record.get("expires_epoch"), 0) <= now_epoch:
            orders.pop(sym, None)

    if action == "BUY":
        removed = bool(orders.pop(symbol, None))
        _write_recent_sell_guard(path, data)
        return {
            "enabled": True,
            "action": action,
            "symbol": symbol,
            "updated": bool(removed),
            "cleared": bool(removed),
            "path": str(path),
        }

    order_qty = _coerce_int(order.get("qty"), 0)
    position_qty_hint = _position_qty_hint_from_order(order)
    remaining_qty_hint = max(0, position_qty_hint - order_qty) if position_qty_hint > 0 else 0
    payload = execution.get("payload") if isinstance(execution.get("payload"), dict) else {}
    orders[symbol] = {
        "symbol": symbol,
        "last_sell_epoch": int(now_epoch),
        "expires_epoch": int(now_epoch + ttl_sec),
        "ttl_sec": int(ttl_sec),
        "order_id": str(execution.get("order_id") or execution.get("ord_no") or payload.get("order_id") or ""),
        "run_id": str(state.get("run_id") or ""),
        "last_sell_qty": int(order_qty),
        "position_qty_hint": int(position_qty_hint),
        "remaining_qty_hint": int(remaining_qty_hint),
        "effective_mode": str(_execution_mode_details().get("effective_mode") or ""),
    }
    _write_recent_sell_guard(path, data)
    return {
        "enabled": True,
        "action": action,
        "symbol": symbol,
        "updated": True,
        "remaining_qty_hint": int(remaining_qty_hint),
        "expires_epoch": int(now_epoch + ttl_sec),
        "ttl_sec": int(ttl_sec),
        "path": str(path),
    }


def _resolve_mock_cash_available(state: Dict[str, Any]) -> float:
    persisted = state.get("persisted_state")
    if isinstance(persisted, dict):
        cash = _coerce_float(persisted.get("mock_cash"), 0.0)
        if cash > 0.0:
            return cash

    port = state.get("portfolio_snapshot")
    if isinstance(port, dict):
        cash = _coerce_float(port.get("cash"), 0.0)
        if cash > 0.0:
            return cash

    return _coerce_float(os.getenv("MOCK_CASH_FALLBACK"), 0.0)


def _symbol_matches_row(row: Dict[str, Any], symbol: str) -> bool:
    row_symbol = normalize_symbol(row.get("symbol") or row.get("code") or row.get("stk_cd"))
    return not symbol or not row_symbol or row_symbol == symbol


def _positive_price_from_row(row: Dict[str, Any], keys: Tuple[str, ...]) -> Tuple[float, str]:
    for key in keys:
        px = _coerce_float(row.get(key), 0.0)
        if px > 0.0:
            return float(abs(px)), str(key)
    return 0.0, ""


def _canonical_artifact_row(state: Dict[str, Any], agent: str) -> Dict[str, Any]:
    refs = state.get("canonical_artifacts") if isinstance(state.get("canonical_artifacts"), dict) else {}
    path_text = str(refs.get(agent) or "").strip()
    if not path_text:
        return {}
    try:
        path = Path(path_text)
        if not path.exists():
            return {}
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return dict(raw) if isinstance(raw, dict) else {}


def _resolve_order_price_for_notional_with_source(state: Dict[str, Any], order: Dict[str, Any]) -> Tuple[float, str]:
    symbol = _extract_order_symbol(order)
    px = _coerce_float(order.get("price"), 0.0)
    if px > 0.0:
        return float(abs(px)), "order.price"

    px = _coerce_float(order.get("order_price"), 0.0)
    if px > 0.0:
        return float(abs(px)), "order.order_price"

    meta = order.get("meta") if isinstance(order.get("meta"), dict) else {}
    meta_px, meta_key = _positive_price_from_row(
        meta,
        (
            "price",
            "current_price",
            "raw_price",
            "reference_price",
            "monitor_price",
            "signal_price",
            "effective_price",
        ),
    )
    if meta_px > 0.0:
        return float(abs(meta_px)), f"order.meta.{meta_key}"

    price_candidates: list[Tuple[float, str]] = []

    for state_key in (
        "selected",
        "scanner_selected_snapshot",
        "top_candidate",
        "monitor_output",
        "monitor",
        "monitor_snapshot",
        "monitor_state",
    ):
        row = state.get(state_key)
        if not isinstance(row, dict) or not _symbol_matches_row(row, symbol):
            continue
        row_px, row_key = _positive_price_from_row(
            row,
            (
                "price",
                "current_price",
                "effective_price",
                "raw_price",
                "account_current_price",
                "account_mark_price",
                "cur_price",
                "last_price",
                "close",
            ),
        )
        if row_px > 0.0:
            price_candidates.append((row_px, f"{state_key}.{row_key}"))

        position_snapshot = row.get("position_snapshot")
        if isinstance(position_snapshot, dict) and _symbol_matches_row(position_snapshot, symbol):
            position_px, position_key = _positive_price_from_row(
                position_snapshot,
                ("current_price", "price", "mark_price", "avg_price"),
            )
            if position_px > 0.0:
                price_candidates.append((position_px, f"{state_key}.position_snapshot.{position_key}"))

        features = row.get("features")
        if isinstance(features, dict):
            feat_px, feat_key = _positive_price_from_row(
                features,
                ("skill_quote_price", "price", "current_price", "cur_price", "last_price", "close"),
            )
            if feat_px > 0.0:
                price_candidates.append((feat_px, f"{state_key}.features.{feat_key}"))

    quotes = _extract_market_quotes_safe(state)
    quote = quotes.get(symbol) if symbol else None
    if isinstance(quote, dict):
        quote_px, quote_key = _positive_price_from_row(
            quote,
            ("best_ask", "ask", "price", "cur", "current_price", "last_price", "best_bid", "bid"),
        )
        if quote_px > 0.0:
            price_candidates.append((quote_px, f"market.quote.{quote_key}"))

        raw_quote = quote.get("raw") if isinstance(quote.get("raw"), dict) else {}
        raw_rows = raw_quote.get("cntr_infr") if isinstance(raw_quote.get("cntr_infr"), list) else []
        raw_row = raw_rows[0] if raw_rows and isinstance(raw_rows[0], dict) else {}
        if raw_row:
            raw_px, raw_key = _positive_price_from_row(
                raw_row,
                ("pri_sel_bid_unit", "sel_1bid", "cur_prc", "pri_buy_bid_unit", "buy_1bid"),
            )
            if raw_px > 0.0:
                price_candidates.append((raw_px, f"market.quote.raw.{raw_key}"))

    market = state.get("market_snapshot")
    if isinstance(market, dict) and _symbol_matches_row(market, symbol):
        market_px, market_key = _positive_price_from_row(
            market,
            ("best_ask", "ask", "price", "cur", "current_price", "last_price", "best_bid", "bid"),
        )
        if market_px > 0.0:
            price_candidates.append((market_px, f"market_snapshot.{market_key}"))

    canonical_monitor = _canonical_artifact_row(state, "monitor")
    if isinstance(canonical_monitor, dict) and _symbol_matches_row(canonical_monitor, symbol):
        canonical_px, canonical_key = _positive_price_from_row(
            canonical_monitor,
            ("price", "current_price", "effective_price", "raw_price", "cur_price", "last_price", "close"),
        )
        if canonical_px > 0.0:
            price_candidates.append((canonical_px, f"canonical.monitor.{canonical_key}"))

    if not price_candidates:
        return 0.0, ""
    return max(price_candidates, key=lambda item: item[0])


def _resolve_order_price_for_notional(state: Dict[str, Any], order: Dict[str, Any]) -> float:
    price, _source = _resolve_order_price_for_notional_with_source(state, order)
    return price


def _evaluate_mock_cash_guard(state: Dict[str, Any], order: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    if _resolve_execution_mode() != "mock":
        return True, "", {}

    action = str(order.get("action") or "").strip().upper()
    if action != "BUY":
        return True, "", {}

    qty = _coerce_int(order.get("qty"), 0)
    if qty <= 0:
        return True, "", {"qty_evaluable": False}

    price = _resolve_order_price_for_notional(state, order)
    if price <= 0.0:
        # Cannot evaluate notional without price; keep existing behavior.
        return True, "", {"price_evaluable": False}

    cash = _resolve_mock_cash_available(state)
    if cash <= 0.0:
        return True, "", {"cash_evaluable": False}

    notional = float(qty) * float(price)
    details = {
        "cash": float(cash),
        "price": float(price),
        "qty": int(qty),
        "notional": float(notional),
    }
    if notional > cash:
        return False, "insufficient_mock_cash", details
    return True, "", details


def _execution_runtime_clock_input_present(state: Dict[str, Any]) -> bool:
    return _coerce_int(state.get("tick_ts"), 0) > 0 or _coerce_int(state.get("now_epoch"), 0) > 0


def _resolve_execution_minutes_to_close(state: Dict[str, Any]) -> float | None:
    market_context = state.get("market_context") if isinstance(state.get("market_context"), dict) else {}
    existing = None
    if market_context.get("minutes_to_close") not in (None, ""):
        existing = _coerce_float(market_context.get("minutes_to_close"), -1.0)
        if existing < 0.0:
            existing = None

    if not _execution_runtime_clock_input_present(state):
        return existing

    try:
        from libs.runtime.market_hours import MarketHours

        mh = MarketHours()
        epoch = _coerce_int(state.get("tick_ts"), 0) or _coerce_int(state.get("now_epoch"), 0)
        dt_kst = datetime.fromtimestamp(epoch, tz=mh.tz)
        if not mh.is_open(dt_kst):
            return existing
        close_dt = dt_kst.replace(
            hour=mh.close_time.hour,
            minute=mh.close_time.minute,
            second=0,
            microsecond=0,
        )
        computed = max(0.0, (close_dt - dt_kst).total_seconds() / 60.0)
        if existing is not None and abs(float(existing) - float(computed)) <= 1.0:
            return float(existing)
        return float(computed)
    except Exception:
        return existing


def _resolve_execution_buy_closeout_cutoff(state: Dict[str, Any]) -> Tuple[bool, int, int]:
    applied_policy = state.get("applied_policy") if isinstance(state.get("applied_policy"), dict) else {}
    policy = state.get("policy") if isinstance(state.get("policy"), dict) else {}
    applied_monitor = applied_policy.get("monitor") if isinstance(applied_policy.get("monitor"), dict) else {}
    policy_monitor = policy.get("monitor") if isinstance(policy.get("monitor"), dict) else {}
    applied_exit = applied_monitor.get("exit") if isinstance(applied_monitor.get("exit"), dict) else {}
    policy_exit = policy_monitor.get("exit") if isinstance(policy_monitor.get("exit"), dict) else {}
    applied_eod = applied_exit.get("eod_flat") if isinstance(applied_exit.get("eod_flat"), dict) else {}
    policy_eod = policy_exit.get("eod_flat") if isinstance(policy_exit.get("eod_flat"), dict) else {}
    use_eod_flat = (
        applied_eod.get("enabled")
        if applied_eod.get("enabled") is not None
        else policy_eod.get("enabled")
    )
    if use_eod_flat is None and isinstance(policy.get("exit_policy"), dict):
        use_eod_flat = policy["exit_policy"].get("use_eod_flat")
    enabled = _is_trueish(use_eod_flat if use_eod_flat is not None else True)

    eod_raw = applied_eod.get("cutoff_min") if applied_eod.get("cutoff_min") not in (None, "") else policy_eod.get("cutoff_min")
    if eod_raw in (None, "") and isinstance(policy.get("exit_policy"), dict):
        eod_raw = policy["exit_policy"].get("eod_flat_cutoff_min")
    eod_cutoff = max(0, _coerce_int(eod_raw, 10))

    applied_entry = applied_monitor.get("entry") if isinstance(applied_monitor.get("entry"), dict) else {}
    policy_entry = policy_monitor.get("entry") if isinstance(policy_monitor.get("entry"), dict) else {}
    buy_raw = (
        applied_entry.get("buy_closeout_cutoff_min")
        if applied_entry.get("buy_closeout_cutoff_min") not in (None, "")
        else policy_entry.get("buy_closeout_cutoff_min")
    )
    buy_cutoff = _coerce_int(buy_raw, max(15, eod_cutoff))
    if buy_cutoff <= 0:
        buy_cutoff = max(15, eod_cutoff)
    return bool(enabled), int(eod_cutoff), int(max(eod_cutoff, buy_cutoff))


def _evaluate_execution_closeout_buy_guard(state: Dict[str, Any], order: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    action = str(order.get("action") or "").strip().upper()
    if action != "BUY":
        return True, "", {"enabled": False, "action": action}
    use_eod_flat, eod_cutoff, buy_cutoff = _resolve_execution_buy_closeout_cutoff(state)
    minutes_to_close = _resolve_execution_minutes_to_close(state)
    details = {
        "enabled": bool(use_eod_flat),
        "action": action,
        "minutes_to_close": minutes_to_close,
        "eod_flat_cutoff_min": int(eod_cutoff),
        "buy_closeout_cutoff_min": int(buy_cutoff),
    }
    if not use_eod_flat or minutes_to_close is None or minutes_to_close < 0.0:
        details["guard_applied"] = False
        return True, "", details
    details["guard_applied"] = True
    if minutes_to_close <= float(buy_cutoff):
        details["block_reason"] = "buy_blocked_closeout_window"
        return False, "buy_blocked_closeout_window", details
    return True, "", details


def _extract_portfolio_snapshot_health(state: Dict[str, Any]) -> Dict[str, Any]:
    snap = state.get("portfolio_snapshot")
    if isinstance(snap, dict):
        h = snap.get("_health")
        if isinstance(h, dict):
            return dict(h)
    h2 = state.get("portfolio_snapshot_health")
    if isinstance(h2, dict):
        return dict(h2)
    return {}


def _evaluate_portfolio_snapshot_guard(state: Dict[str, Any], order: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    # Guard only in real execution path; mock/offline flow remains unchanged.
    if _resolve_execution_mode() != "real":
        return True, "", {"enabled": False, "reason": "execution_mode_not_real"}

    if not _is_trueish(os.getenv("PORTFOLIO_SNAPSHOT_HEALTH_GUARD_ENABLED", "true")):
        return True, "", {"enabled": False, "reason": "guard_disabled"}

    action = str(order.get("action") or "").strip().upper()
    if action != "BUY":
        return True, "", {"enabled": True, "action": action, "guard_applied": False}

    health = _extract_portfolio_snapshot_health(state)
    if not health:
        return True, "", {"enabled": True, "health_present": False, "guard_applied": True}

    reader_ok = _is_trueish(health.get("reader_ok"))
    positions_mismatch_detected = _is_trueish(health.get("positions_mismatch_detected"))
    reconciliation_applied = _is_trueish(health.get("reconciliation_applied"))
    details: Dict[str, Any] = {
        "enabled": True,
        "health_present": True,
        "reader_ok": bool(reader_ok),
        "source": str(health.get("source") or ""),
        "reader_error": str(health.get("reader_error") or ""),
        "guard_applied": True,
        "positions_source": str(health.get("positions_source") or ""),
        "cash_source": str(health.get("cash_source") or ""),
        "reader_positions_authoritative": _is_trueish(health.get("reader_positions_authoritative")),
        "positions_mismatch_detected": bool(positions_mismatch_detected),
        "reconciliation_applied": bool(reconciliation_applied),
        "reconciliation_status": str(health.get("reconciliation_status") or ""),
        "reader_positions_count": _coerce_int(health.get("reader_positions_count"), 0),
        "persisted_positions_count": _coerce_int(health.get("persisted_positions_count"), 0),
    }
    if reader_ok:
        if positions_mismatch_detected and not reconciliation_applied:
            return False, "portfolio_snapshot_positions_mismatch_unresolved", details
        return True, "", details
    return False, "portfolio_snapshot_reader_error", details


def _is_degrade_mode(state: Dict[str, Any]) -> bool:
    resilience = state.get("resilience")
    if not isinstance(resilience, dict):
        return False
    return _is_trueish(resilience.get("degrade_mode"))


def _is_manual_approved(state: Dict[str, Any], exec_context: Dict[str, Any]) -> bool:
    if _is_trueish(state.get("execution_manual_approved")):
        return True
    if _is_trueish(state.get("manual_approved")):
        return True
    if _is_trueish(exec_context.get("manual_approved")):
        return True
    approval_status = str(exec_context.get("approval_status") or "").strip().lower()
    return approval_status in ("approved", "manual_approved")


def _degrade_notional_ratio(state: Dict[str, Any]) -> float:
    policy = state.get("resilience_policy") if isinstance(state.get("resilience_policy"), dict) else {}
    ratio = _coerce_float(policy.get("degrade_notional_ratio"), _coerce_float(os.getenv("DEGRADE_NOTIONAL_RATIO"), 0.25))
    if ratio <= 0:
        return 0.0
    if ratio > 1.0:
        return 1.0
    return ratio


def _evaluate_degrade_execution_policy(
    *,
    state: Dict[str, Any],
    order: Dict[str, Any],
    exec_context: Dict[str, Any],
) -> Tuple[bool, str, Dict[str, Any]]:
    if not _is_degrade_mode(state):
        return True, "", {"degrade_mode": False}

    details: Dict[str, Any] = {"degrade_mode": True}

    # M23-5 policy: degrade mode disables effective auto-approval.
    if not _is_manual_approved(state, exec_context):
        details["required"] = "manual_approval"
        return False, "degrade_manual_approval_required", details

    # Allowlist remains an optional guard; enforce membership only when configured.
    allow = _parse_symbol_allowlist(os.getenv("SYMBOL_ALLOWLIST"))
    details["allowlist_size"] = len(allow)
    sym = _extract_order_symbol(order)
    if allow and sym and sym not in allow:
        details["symbol"] = sym
        return False, "degrade_symbol_not_allowlisted", details

    max_notional = _coerce_int(os.getenv("MAX_ORDER_NOTIONAL"), 0)
    ratio = _degrade_notional_ratio(state)
    details["degrade_notional_ratio"] = ratio
    details["max_order_notional"] = max_notional
    if max_notional <= 0 or ratio <= 0:
        return True, "", details

    effective_limit = max(1, int(max_notional * ratio))
    details["effective_max_notional"] = effective_limit

    action = str(order.get("action") or "").strip().upper()
    qty = _coerce_int(order.get("qty"), 0)
    if qty <= 0:
        return True, "", details

    px_raw = order.get("price")
    price_source = "order.price"
    if px_raw is not None:
        try:
            px = int(px_raw)
        except Exception:
            details["invalid_price"] = str(px_raw)
            return False, "degrade_invalid_price_for_notional_guard", details
    else:
        price, price_source = _resolve_order_price_for_notional_with_source(state, order)
        details["price_source"] = str(price_source)
        if price <= 0.0:
            if action == "BUY":
                details["price_evaluable"] = False
                return False, "degrade_missing_price_for_notional_guard", details
            return True, "", details
        px = int(price)

    notional = qty * px
    details["price"] = float(px)
    details["price_source"] = str(price_source)
    details["order_notional"] = notional
    if notional > effective_limit:
        return False, "degrade_notional_limit_exceeded", details

    return True, "", details


def _build_order_from_intent(intent: Dict[str, Any]) -> Dict[str, Any]:
    """Best-effort order dict. This is intentionally thin.

    Real request shaping should be done via ApiRequestBuilder + ApiSpec.
    """
    # Allow multiple intent schemas during transition
    action = intent.get("action") or intent.get("intent") or intent.get("type") or "NOOP"
    action = str(action).upper()
    api_id = intent.get("order_api_id") or intent.get("api_id") or "ORDER_SUBMIT"
    order_type = intent.get("order_type") or intent.get("type") or "limit"
    order_type = str(order_type or "limit").strip().lower()

    qty = intent.get("qty") or intent.get("quantity")
    meta = intent.get("meta") if isinstance(intent.get("meta"), dict) else {}
    price = intent.get("price")
    if price in (None, ""):
        for candidate in (
            meta.get("price"),
            meta.get("current_price"),
            meta.get("raw_price"),
            meta.get("quote_price"),
            meta.get("market_price"),
        ):
            if candidate not in (None, ""):
                price = candidate
                break
    raw_symbol = intent.get("symbol") or intent.get("code") or intent.get("stk_cd")
    symbol = normalize_symbol(raw_symbol)

    qty_int = None
    if qty is not None:
        try:
            qty_int = int(float(qty))
        except Exception:
            qty_int = None

    price_int = None
    if price is not None:
        try:
            price_int = int(float(price))
        except Exception:
            price_int = None

    order: Dict[str, Any] = {
        "api_id": api_id,
        "action": action,
        "symbol": symbol,
        "symbol_raw": raw_symbol,
        "qty": qty_int if qty_int is not None else qty,
        "price": price_int if price_int is not None else price,
        "order_type": order_type,
        "tif": intent.get("tif") or intent.get("time_in_force"),
        "rationale": intent.get("rationale") or intent.get("reason") or "",
    }

    # Add Kiwoom order-body aliases used by kt10000/kt10001 specs.
    if action in ("BUY", "SELL"):
        trde_tp = intent.get("trde_tp")
        if trde_tp is None or not str(trde_tp).strip():
            trde_tp = "3" if order_type == "market" else "0"
        ord_qty = "" if qty_int is None else str(max(0, int(qty_int)))
        ord_uv = ""
        if order_type != "market" and price_int is not None:
            ord_uv = str(max(0, int(price_int)))
        order["dmst_stex_tp"] = intent.get("dmst_stex_tp") or intent.get("market") or "KRX"
        order["stk_cd"] = symbol
        order["ord_qty"] = ord_qty
        order["ord_uv"] = ord_uv
        order["trde_tp"] = str(trde_tp)
        order["cond_uv"] = intent.get("cond_uv") or ""

    # Pass through any extra keys (so request builder can pick them up)
    for k, v in intent.items():
        if k not in order:
            order[k] = v
    return order


def _apply_mock_broker_order_safety(order: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize broker-facing order for Kiwoom mock REST compatibility.

    In mock broker HTTP mode, market orders are safer/reproducible than limit
    for LLM-generated intents. We coerce BUY/SELL orders to market semantics.
    """
    if not _is_kiwoom_mock_broker_http_mode():
        return order

    action = str(order.get("action") or "").strip().upper()
    if action not in ("BUY", "SELL"):
        return order

    cur_type = str(order.get("order_type") or "limit").strip().lower()
    if cur_type == "market":
        return order

    order["order_type"] = "market"
    # Kiwoom body aliases
    order["trde_tp"] = "3"
    order["ord_uv"] = ""

    rationale = str(order.get("rationale") or "").strip()
    tag = "mock_broker_force_market"
    if not rationale:
        order["rationale"] = tag
    elif tag not in rationale:
        order["rationale"] = f"{rationale};{tag}"
    return order


def _broker_code_success(value: Any) -> Optional[bool]:
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


def _infer_execution_ok(payload: Dict[str, Any]) -> Tuple[bool, str]:
    broker = _broker_code_success(payload.get("broker_code"))
    if broker is not None:
        return bool(broker), "broker_code"

    if "api_ok" in payload:
        return bool(payload.get("api_ok")), "api_ok"

    status_code = payload.get("status_code")
    try:
        code = int(float(status_code))
        return (200 <= code < 300), "status_code"
    except Exception:
        pass

    if str(payload.get("mode") or "").strip().lower() == "mock":
        return True, "mode_mock_default"

    # Backward-compatible default when no execution signal exists.
    return True, "default_true"


def _supervisor_allow(supervisor: Any, order: Dict[str, Any], risk: Dict[str, Any]) -> Any:
    """Supervisor API changed during refactors.

    Current Supervisor.allow signature in libs/risk/supervisor.py:
      allow(intent: str, context: Dict[str,Any]) -> AllowResult
    """
    action = order.get("action") or order.get("intent") or "NOOP"
    action = str(action).lower().strip()
    ctx = dict(risk); ctx["order"] = order
    try:
        return supervisor.allow(action, ctx)
    except TypeError:
        # legacy keyword versions
        try:
            return supervisor.allow(intent=action, context=ctx)
        except TypeError:
            return supervisor.allow(action, ctx)


def _extract_strategy_policy(packet: Dict[str, Any], state: Dict[str, Any]) -> Dict[str, Any]:
    raw = packet.get("strategy_policy")
    if isinstance(raw, dict) and raw:
        return dict(raw)
    strategist_output = state.get("strategist_output")
    if isinstance(strategist_output, dict):
        raw = strategist_output.get("strategy_policy")
        if isinstance(raw, dict) and raw:
            return dict(raw)
    raw = state.get("strategy_policy")
    if isinstance(raw, dict) and raw:
        return dict(raw)
    return {}


def _summarize_strategy_policy(strategy_policy: Dict[str, Any], packet: Dict[str, Any]) -> Dict[str, Any]:
    packet_summary = packet.get("strategy_policy_summary")
    if isinstance(packet_summary, dict) and packet_summary:
        return dict(packet_summary)
    if not isinstance(strategy_policy, dict) or not strategy_policy:
        return {}

    market_policy = strategy_policy.get("market_policy") if isinstance(strategy_policy.get("market_policy"), dict) else {}
    entry_policy = strategy_policy.get("entry_policy") if isinstance(strategy_policy.get("entry_policy"), dict) else {}
    position_sizing = entry_policy.get("position_sizing") if isinstance(entry_policy.get("position_sizing"), dict) else {}
    monitor_policy = strategy_policy.get("monitor_policy") if isinstance(strategy_policy.get("monitor_policy"), dict) else {}
    hard_risk_rails = monitor_policy.get("hard_risk_rails") if isinstance(monitor_policy.get("hard_risk_rails"), dict) else {}
    decision_policy = strategy_policy.get("decision_policy") if isinstance(strategy_policy.get("decision_policy"), dict) else {}
    return {
        "schema_version": str(strategy_policy.get("schema_version") or "strategy_policy.v1"),
        "playbook": str(market_policy.get("playbook") or ""),
        "risk_tone": str(market_policy.get("risk_tone") or ""),
        "trade_aggressiveness": str(market_policy.get("trade_aggressiveness") or ""),
        "defensive_mode": bool(market_policy.get("defensive_mode", False)),
        "max_position_qty": _coerce_int(position_sizing.get("max_position_qty"), 0),
        "min_position_qty": _coerce_int(position_sizing.get("min_position_qty"), 0),
        "lot_size": _coerce_int(position_sizing.get("lot_size"), 0),
        "hard_stop_pct": _coerce_float(hard_risk_rails.get("hard_stop_pct"), 0.0),
        "max_stop_pct_cap": _coerce_float(hard_risk_rails.get("max_stop_pct_cap"), 0.0),
        "use_strategy_v1_engine": _is_trueish(decision_policy.get("use_strategy_v1_engine")),
        "allow_score_override": _is_trueish(decision_policy.get("allow_score_override")),
    }


def _augment_supervisor_risk_context(
    *,
    state: Dict[str, Any],
    packet: Dict[str, Any],
    order: Dict[str, Any],
    risk: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    strategy_policy = _extract_strategy_policy(packet, state)
    strategy_policy_summary = _summarize_strategy_policy(strategy_policy, packet)
    enriched = dict(risk or {})
    enriched["order"] = dict(order or {})
    if strategy_policy:
        enriched["strategy_policy"] = dict(strategy_policy)
    if strategy_policy_summary:
        enriched["strategy_policy_summary"] = dict(strategy_policy_summary)

    qty = _coerce_int(order.get("qty"), 0)
    price, price_source = _resolve_order_price_for_notional_with_source(state, order)
    if qty > 0:
        enriched["order_qty"] = int(qty)
    if price > 0:
        enriched["order_price"] = float(price)
        enriched["order_price_source"] = str(price_source)
    if qty > 0 and price > 0:
        enriched["order_notional"] = float(qty) * float(price)
    return enriched, strategy_policy_summary


def _prepare_request(order: Dict[str, Any], catalog: Any) -> Any:
    """Build a PreparedRequest-like object for executors.

    - If api_id exists and catalog can load an ApiSpec, use ApiRequestBuilder.
    - Otherwise fall back to a SimpleNamespace with required attrs.
    """
    api_id_raw = str(order.get("api_id") or order.get("order_api_id") or "").strip()
    action = str(order.get("action") or "").strip().upper()
    api_candidates = []
    if api_id_raw:
        api_candidates.append(api_id_raw)

    # Resolve canonical order alias only when target API exists in current catalog.
    if api_id_raw.upper() == "ORDER_SUBMIT":
        alias = ""
        if action == "BUY":
            alias = "kt10000"
        elif action == "SELL":
            alias = "kt10001"
        if alias:
            try:
                spec_alias = None
                for meth in ("get", "get_api", "lookup"):
                    if hasattr(catalog, meth):
                        try:
                            spec_alias = getattr(catalog, meth)(alias)
                        except Exception:
                            spec_alias = None
                        break
                if spec_alias is not None and alias not in api_candidates:
                    api_candidates.append(alias)
            except Exception:
                pass

    for api_id in api_candidates:
        # Build from spec + context (preferred)
        try:
            spec = None
            for meth in ("get", "get_api", "lookup"):
                if hasattr(catalog, meth):
                    try:
                        spec = getattr(catalog, meth)(api_id)
                    except Exception:
                        spec = None
                    break

            if spec is not None:
                ApiRequestBuilder = _import_request_builder()
                Settings = _import_settings()
                s = Settings.from_env()
                ctx: Dict[str, Any] = dict(order)
                # provide common aliases expected by builder
                ctx.setdefault("account_no", s.kiwoom_account_no)
                ctx.setdefault("account", s.kiwoom_account_no)

                rb = ApiRequestBuilder()
                res = rb.prepare(spec, ctx)

                if str(getattr(res, "action", "")).strip().lower() == "ready" and getattr(res, "request", None) is not None:
                    req = res.request
                    # ensure attributes expected by executors exist
                    if getattr(req, "query", None) is None:
                        setattr(req, "query", getattr(req, "params", {}) or {})
                    if getattr(req, "headers", None) is None:
                        setattr(req, "headers", {})
                    if getattr(req, "body", None) is None:
                        setattr(req, "body", {})
                    return req

                # not ready -> fall back to a safe NOOP request with hint
                return SimpleNamespace(
                    method="POST",
                    path="/__missing_params__",
                    headers={},
                    query={},
                    body={"missing": res.missing, "api_id": api_id},
                )
        except Exception:
            continue

    # Fallback: minimal request
    return SimpleNamespace(
        method="POST",
        path="/orders",
        headers={},
        query={},
        body={k: v for k, v in order.items() if k not in ("headers", "query")},
    )


def _normalize_execution(
    *,
    allowed: bool,
    execution_result: Any,
    allow_result: Any,
    order: Dict[str, Any],
    reason: str = "",
    strategy_policy_summary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Normalize to dict shape used by tests and reports."""
    exec_mode = _resolve_execution_mode()
    exec_meta = _execution_mode_details()
    resolved_reason = str(reason or "")
    if not resolved_reason and allow_result is not None:
        resolved_reason = str(getattr(allow_result, "reason", "") or "")

    payload: Dict[str, Any] = {}
    if execution_result is None:
        payload = {"mode": exec_mode}
    else:
        # ExecutionResult dataclass
        if hasattr(execution_result, "payload"):
            p = getattr(execution_result, "payload")
            if isinstance(p, dict):
                payload = dict(p)
        # If still empty, build from response/meta
        if not payload:
            if hasattr(execution_result, "response") and getattr(execution_result, "response") is not None:
                r = getattr(execution_result, "response")
                payload["status_code"] = getattr(r, "status_code", None)
                payload["api_ok"] = bool(getattr(r, "ok", False))
                raw_text = getattr(r, "raw_text", None)
                if raw_text is None:
                    raw_text = getattr(r, "text", None)
                payload["text"] = raw_text

                response_payload = getattr(r, "payload", None)
                if isinstance(response_payload, dict):
                    response_payload = dict(response_payload)
                    payload["response_payload"] = response_payload
                    payload["json"] = response_payload

                    for k in ("ord_no", "order_id", "orderId", "odno", "ODNO", "ordNo"):
                        v = response_payload.get(k)
                        if v is not None and str(v).strip():
                            payload["order_id"] = str(v).strip()
                            break

                    for k in ("msg_cd", "message_code", "code", "rt_cd", "error_code", "err_cd", "return_code"):
                        v = response_payload.get(k)
                        if v is not None and str(v).strip():
                            payload["broker_code"] = str(v).strip()
                            break

                    for k in ("msg1", "msg", "message", "return_msg", "error_message"):
                        v = response_payload.get(k)
                        if v is not None and str(v).strip():
                            payload["broker_message"] = str(v).strip()
                            break
                else:
                    payload["json"] = getattr(r, "json", None)

                err_code = getattr(r, "error_code", None)
                if err_code is not None and str(err_code).strip():
                    payload["error_code"] = str(err_code).strip()

                err_msg = getattr(r, "error_message", None)
                if err_msg is not None and str(err_msg).strip():
                    payload["error_message"] = str(err_msg).strip()
            if hasattr(execution_result, "meta") and getattr(execution_result, "meta") is not None:
                payload["meta"] = getattr(execution_result, "meta")
        payload.setdefault("mode", exec_mode)

    for key, value in exec_meta.items():
        payload.setdefault(key, value)

    response_payload = payload.get("response_payload") if isinstance(payload.get("response_payload"), dict) else {}
    top_level_order_id = str(
        payload.get("order_id")
        or payload.get("ord_no")
        or response_payload.get("order_id")
        or response_payload.get("ord_no")
        or ""
    ).strip()
    top_level_broker_message = str(
        payload.get("broker_message")
        or response_payload.get("return_msg")
        or payload.get("error_message")
        or ""
    ).strip()
    top_level_broker_code = str(
        payload.get("broker_code")
        or response_payload.get("msg_cd")
        or response_payload.get("return_code")
        or payload.get("error_code")
        or ""
    ).strip()
    top_level_filled_price = (
        payload.get("filled_price")
        if payload.get("filled_price") not in (None, "")
        else payload.get("avg_fill_price")
        if payload.get("avg_fill_price") not in (None, "")
        else payload.get("avg_price")
    )
    top_level_filled_qty = (
        payload.get("filled_qty")
        if payload.get("filled_qty") not in (None, "")
        else payload.get("qty")
    )
    top_level_status = str(
        payload.get("fill_status")
        or payload.get("status")
        or response_payload.get("return_msg")
        or ""
    ).strip()

    ok = bool(allowed)
    ok_source = "allowed_gate"
    if allowed and execution_result is not None:
        ok, ok_source = _infer_execution_ok(payload)
        if not ok:
            cur = resolved_reason.strip().lower()
            if cur in ("", "allowed"):
                bcode = str(payload.get("broker_code") or "").strip()
                resolved_reason = f"broker_rejected:{bcode}" if bcode else "broker_rejected"

    verdict = {
        "allowed": bool(allowed),
        "ok": bool(ok),
        "execution_ok": bool(ok),
        "ok_source": str(ok_source),
        "reason": resolved_reason,
        "order_id": top_level_order_id,
        "ord_no": top_level_order_id,
        "broker_code": top_level_broker_code,
        "broker_message": top_level_broker_message,
        "status": top_level_status,
        "filled_price": top_level_filled_price,
        "filled_qty": top_level_filled_qty,
        "execution_mode": str(payload.get("execution_mode") or "").strip(),
        "kiwoom_mode": str(payload.get("kiwoom_mode") or "").strip(),
        "broker_env": str(payload.get("broker_env") or "").strip(),
        "effective_mode": str(payload.get("effective_mode") or "").strip(),
        "order": order,
        "payload": payload,
    }
    if isinstance(strategy_policy_summary, dict) and strategy_policy_summary:
        verdict["strategy_policy_summary"] = dict(strategy_policy_summary)
        payload.setdefault("strategy_policy_summary", dict(strategy_policy_summary))
    return verdict


def _append_execution_trace_entries(
    state: Dict[str, Any],
    *,
    order: Dict[str, Any],
    execution: Dict[str, Any],
    allow_result: Any = None,
    strategy_policy_summary: Optional[Dict[str, Any]] = None,
) -> None:
    action = str(order.get("action") or "").strip().upper()
    reason = str(execution.get("reason") or "")
    allowed = bool(execution.get("allowed"))
    ok = bool(execution.get("ok"))
    payload = execution.get("payload") if isinstance(execution.get("payload"), dict) else {}

    supervisor_allow: Optional[bool] = None
    supervisor_reason = ""
    supervisor_details: Dict[str, Any] = {}
    if allow_result is not None:
        supervisor_allow = bool(getattr(allow_result, "allowed", getattr(allow_result, "allow", False)))
        supervisor_reason = str(getattr(allow_result, "reason", "") or "")
        raw_details = getattr(allow_result, "details", {})
        if isinstance(raw_details, dict):
            supervisor_details = dict(raw_details)

    append_decision_trace(
        state,
        agent="supervisor",
        event="verdict",
        payload={
            "verdict": "approve" if allowed else "reject",
            "guard_reason": reason or supervisor_reason,
            "supervisor_allow": supervisor_allow,
            "supervisor_reason": supervisor_reason,
            "supervisor_details": supervisor_details,
            "action": action,
            "symbol": str(order.get("symbol") or ""),
            "strategy_policy_summary": dict(strategy_policy_summary or {}),
        },
    )

    execution_attempted = bool(allowed and action in ("BUY", "SELL"))
    if not execution_attempted:
        fill_status = "not_attempted"
    elif ok:
        fill_status = "accepted_or_filled"
    else:
        fill_status = "rejected"

    append_decision_trace(
        state,
        agent="executor",
        event="result",
        payload={
            "execution_attempted": execution_attempted,
            "order_result": {
                "ok": ok,
                "reason": reason,
                "mode": str(payload.get("mode") or ""),
                "broker_code": str(payload.get("broker_code") or ""),
                "broker_message": str(payload.get("broker_message") or ""),
                "order_id": str(payload.get("order_id") or ""),
            },
            "fill_status_summary": fill_status,
            "strategy_policy_summary": dict(strategy_policy_summary or {}),
        },
    )


def execute_from_packet(state: dict) -> dict:
    """Execute directly from a TradeDecisionPacket.

    Expects:
      - state['decision_packet']  # dict form
      - state['catalog_path'] optional (fallback: env KIWOOM_API_CATALOG_PATH)
      - state['run_id'] optional (auto-generate if missing)
      - optional: state['executor'] injected for tests
      - optional: state['supervisor'] injected for tests

    Produces:
      - state['execution'] (dict)
    """
    EventLogger, new_run_id = _import_event_logger()
    from libs.core.event_logger import resolve_event_log_path

    logger = EventLogger(log_path=resolve_event_log_path())

    run_id = state.get("run_id") or new_run_id()
    state["run_id"] = run_id
    logger.log(run_id=run_id, stage="execute_from_packet", event="start", payload={})

    ApiCatalog = _import_api_catalog()
    Supervisor = _import_supervisor()
    get_executor = _import_get_executor()

    order: Dict[str, Any] = {}
    allow_result: Any = None
    portfolio_details: Dict[str, Any] = {}
    strategy_policy_summary: Dict[str, Any] = {}

    def _quote_snapshot_for_order(order_obj: Dict[str, Any]) -> Dict[str, Any]:
        symbol = _extract_order_symbol(order_obj)
        if not symbol:
            return {}
        quote = _augment_quote_snapshot_with_spread(_extract_upper_limit_quote_snapshot(state, symbol))
        if not bool(quote.get("quote_present")) and not any(
            _coerce_float(quote.get(key), 0.0) > 0.0 for key in ("best_bid", "best_ask", "spread_bps")
        ):
            return {}
        return quote

    def _ensure_execution_quote_snapshot(execution_payload: Dict[str, Any]) -> Dict[str, Any]:
        execution_obj = execution_payload if isinstance(execution_payload, dict) else {}
        quote_snapshot = execution_obj.get("quote_snapshot") if isinstance(execution_obj.get("quote_snapshot"), dict) else {}
        if not quote_snapshot:
            payload_obj = execution_obj.get("payload") if isinstance(execution_obj.get("payload"), dict) else {}
            quote_snapshot = payload_obj.get("quote_snapshot") if isinstance(payload_obj.get("quote_snapshot"), dict) else {}
        if not quote_snapshot:
            quote_snapshot = _quote_snapshot_for_order(order)
        if not quote_snapshot:
            return execution_obj
        quote_snapshot = _augment_quote_snapshot_with_spread(quote_snapshot)
        execution_obj["quote_snapshot"] = dict(quote_snapshot)
        for key in ("best_bid", "best_ask", "spread_bps"):
            value = quote_snapshot.get(key)
            if value not in (None, "", 0, 0.0):
                execution_obj[key] = float(_coerce_float(value, 0.0))
        payload_obj = execution_obj.get("payload") if isinstance(execution_obj.get("payload"), dict) else {}
        if payload_obj is not None:
            payload_obj = dict(payload_obj)
            payload_obj.setdefault("quote_snapshot", dict(quote_snapshot))
            for key in ("best_bid", "best_ask", "spread_bps"):
                value = quote_snapshot.get(key)
                if value not in (None, "", 0, 0.0):
                    payload_obj.setdefault(key, float(_coerce_float(value, 0.0)))
            execution_obj["payload"] = payload_obj
        return execution_obj

    def _persist_execution_artifacts(*, supervisor_allowed: bool, supervisor_reason: str, supervisor_details: Dict[str, Any] | None = None) -> None:
        try:
            write_supervisor_artifact(
                state,
                order=order,
                allowed=bool(supervisor_allowed),
                reason=str(supervisor_reason or ""),
                details=dict(supervisor_details or {}),
                strategy_policy_summary=dict(strategy_policy_summary or {}),
            )
        except Exception:
            pass
        try:
            execution_payload = state.get("execution") if isinstance(state.get("execution"), dict) else {}
            if execution_payload:
                _ensure_execution_quote_snapshot(execution_payload)
                write_executor_artifact(state, execution=execution_payload, order=order)
        except Exception:
            pass
    try:
        packet: Dict[str, Any] = state["decision_packet"]

        catalog_path = state.get("catalog_path") or _catalog_path_from_env()
        catalog = ApiCatalog.load(catalog_path)

        supervisor = state.get("supervisor")
        if supervisor is None:
            if hasattr(Supervisor, "from_settings"):
                supervisor = Supervisor.from_settings()
            else:
                supervisor = Supervisor()
        executor = state.get("executor") or get_executor()

        intent = packet.get("intent") or {}
        risk = packet.get("risk") or {}
        exec_context = packet.get("exec_context") or {}

        # Build order dict
        if state.get("order_builder") is not None:
            order = state["order_builder"](intent, catalog)  # type: ignore[call-arg]
        else:
            order = _build_order_from_intent(intent)
        order = _apply_mock_broker_order_safety(order)
        risk_for_supervisor, strategy_policy_summary = _augment_supervisor_risk_context(
            state=state,
            packet=packet,
            order=order,
            risk=risk,
        )

        action = str(order.get("action") or "").strip().upper()
        if action == "NOOP":
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=None,
                order=order,
                reason="noop_intent_skipped",
                strategy_policy_summary=strategy_policy_summary,
            )
            _append_execution_trace_entries(
                state,
                order=order,
                execution=state["execution"],
                allow_result=None,
                strategy_policy_summary=strategy_policy_summary,
            )
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="verdict",
                payload={"allowed": False, "reason": "noop_intent_skipped", "strategy_policy_summary": strategy_policy_summary},
            )
            _persist_execution_artifacts(supervisor_allowed=False, supervisor_reason="noop_intent_skipped")
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        closeout_buy_allowed, closeout_buy_reason, closeout_buy_details = _evaluate_execution_closeout_buy_guard(state, order)
        if not closeout_buy_allowed:
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=None,
                order=order,
                reason=closeout_buy_reason,
                strategy_policy_summary=strategy_policy_summary,
            )
            state["execution"]["closeout_buy_guard"] = closeout_buy_details
            _append_execution_trace_entries(
                state,
                order=order,
                execution=state["execution"],
                allow_result=None,
                strategy_policy_summary=strategy_policy_summary,
            )
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="closeout_buy_guard_block",
                payload={"allowed": False, "reason": closeout_buy_reason, **closeout_buy_details},
            )
            _persist_execution_artifacts(
                supervisor_allowed=False,
                supervisor_reason=closeout_buy_reason,
                supervisor_details=closeout_buy_details,
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        symbol_format_allowed, symbol_format_reason, symbol_format_details = _evaluate_symbol_format_guard(order)
        if not symbol_format_allowed:
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=None,
                order=order,
                reason=symbol_format_reason,
                strategy_policy_summary=strategy_policy_summary,
            )
            state["execution"]["symbol_format_guard"] = symbol_format_details
            _append_execution_trace_entries(
                state, order=order, execution=state["execution"], allow_result=None, strategy_policy_summary=strategy_policy_summary
            )
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="symbol_format_guard_block",
                payload={"allowed": False, "reason": symbol_format_reason, **symbol_format_details},
            )
            _persist_execution_artifacts(
                supervisor_allowed=False,
                supervisor_reason=symbol_format_reason,
                supervisor_details=symbol_format_details,
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        symbol_allowed, symbol_reason, symbol_details = _evaluate_symbol_allowlist_guard(order)
        if not symbol_allowed:
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=None,
                order=order,
                reason=symbol_reason,
                strategy_policy_summary=strategy_policy_summary,
            )
            state["execution"]["symbol_guard"] = symbol_details
            _append_execution_trace_entries(
                state, order=order, execution=state["execution"], allow_result=None, strategy_policy_summary=strategy_policy_summary
            )
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="symbol_guard_block",
                payload={"allowed": False, "reason": symbol_reason, **symbol_details},
            )
            _persist_execution_artifacts(
                supervisor_allowed=False,
                supervisor_reason=symbol_reason,
                supervisor_details=symbol_details,
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        asset_allowed, asset_reason, asset_details = _evaluate_asset_universe_guard(state, order)
        if not asset_allowed:
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=None,
                order=order,
                reason=asset_reason,
                strategy_policy_summary=strategy_policy_summary,
            )
            state["execution"]["asset_universe_guard"] = asset_details
            _append_execution_trace_entries(
                state, order=order, execution=state["execution"], allow_result=None, strategy_policy_summary=strategy_policy_summary
            )
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="asset_universe_guard_block",
                payload={"allowed": False, "reason": asset_reason, **asset_details},
            )
            _persist_execution_artifacts(
                supervisor_allowed=False,
                supervisor_reason=asset_reason,
                supervisor_details=asset_details,
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        restricted_allowed, restricted_reason, restricted_details = _evaluate_mock_broker_restricted_symbol_guard(state, order)
        if not restricted_allowed:
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=None,
                order=order,
                reason=restricted_reason,
                strategy_policy_summary=strategy_policy_summary,
            )
            state["execution"]["mock_broker_restricted_symbol_guard"] = restricted_details
            _append_execution_trace_entries(
                state, order=order, execution=state["execution"], allow_result=None, strategy_policy_summary=strategy_policy_summary
            )
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="mock_broker_restricted_symbol_block",
                payload={"allowed": False, "reason": restricted_reason, **restricted_details},
            )
            _persist_execution_artifacts(
                supervisor_allowed=False,
                supervisor_reason=restricted_reason,
                supervisor_details=restricted_details,
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        upper_limit_allowed, upper_limit_reason, upper_limit_details = _evaluate_upper_limit_buy_guard(state, order)
        if not upper_limit_allowed:
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=None,
                order=order,
                reason=upper_limit_reason,
                strategy_policy_summary=strategy_policy_summary,
            )
            state["execution"]["upper_limit_guard"] = upper_limit_details
            _append_execution_trace_entries(
                state, order=order, execution=state["execution"], allow_result=None, strategy_policy_summary=strategy_policy_summary
            )
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="upper_limit_guard_block",
                payload={"allowed": False, "reason": upper_limit_reason, **upper_limit_details},
            )
            _persist_execution_artifacts(
                supervisor_allowed=False,
                supervisor_reason=upper_limit_reason,
                supervisor_details=upper_limit_details,
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        limits_allowed, limits_reason, limits_details = _evaluate_order_limit_guard(state, order)
        if not limits_allowed:
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=None,
                order=order,
                reason=limits_reason,
                strategy_policy_summary=strategy_policy_summary,
            )
            state["execution"]["order_limit_guard"] = limits_details
            _append_execution_trace_entries(
                state, order=order, execution=state["execution"], allow_result=None, strategy_policy_summary=strategy_policy_summary
            )
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="order_limit_guard_block",
                payload={"allowed": False, "reason": limits_reason, **limits_details},
            )
            _persist_execution_artifacts(
                supervisor_allowed=False,
                supervisor_reason=limits_reason,
                supervisor_details=limits_details,
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        portfolio_allowed, portfolio_reason, portfolio_details = _evaluate_portfolio_snapshot_guard(state, order)
        if not portfolio_allowed:
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=None,
                order=order,
                reason=portfolio_reason,
                strategy_policy_summary=strategy_policy_summary,
            )
            state["execution"]["portfolio_guard"] = portfolio_details
            _append_execution_trace_entries(
                state, order=order, execution=state["execution"], allow_result=None, strategy_policy_summary=strategy_policy_summary
            )
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="portfolio_guard_block",
                payload={"allowed": False, "reason": portfolio_reason, "portfolio_guard": portfolio_details, **portfolio_details},
            )
            _persist_execution_artifacts(
                supervisor_allowed=False,
                supervisor_reason=portfolio_reason,
                supervisor_details=portfolio_details,
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        if _should_block_duplicate_mock_buy(state, order):
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=None,
                order=order,
                reason="duplicate_buy_position_exists",
                strategy_policy_summary=strategy_policy_summary,
            )
            state["execution"]["portfolio_guard"] = portfolio_details
            _append_execution_trace_entries(
                state, order=order, execution=state["execution"], allow_result=None, strategy_policy_summary=strategy_policy_summary
            )
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="verdict",
                payload={"allowed": False, "reason": "duplicate_buy_position_exists", "portfolio_guard": portfolio_details},
            )
            _persist_execution_artifacts(
                supervisor_allowed=False,
                supervisor_reason="duplicate_buy_position_exists",
                supervisor_details=portfolio_details,
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        recent_buy_allowed, recent_buy_reason, recent_buy_details = _evaluate_recent_buy_order_guard(state, order)
        if not recent_buy_allowed:
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=None,
                order=order,
                reason=recent_buy_reason,
                strategy_policy_summary=strategy_policy_summary,
            )
            state["execution"]["portfolio_guard"] = portfolio_details
            state["execution"]["recent_buy_order_guard"] = recent_buy_details
            _append_execution_trace_entries(
                state, order=order, execution=state["execution"], allow_result=None, strategy_policy_summary=strategy_policy_summary
            )
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="recent_buy_order_guard_block",
                payload={"allowed": False, "reason": recent_buy_reason, "portfolio_guard": portfolio_details, **recent_buy_details},
            )
            _persist_execution_artifacts(
                supervisor_allowed=False,
                supervisor_reason=recent_buy_reason,
                supervisor_details={**dict(portfolio_details or {}), **dict(recent_buy_details or {})},
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        recent_sell_allowed, recent_sell_reason, recent_sell_details = _evaluate_recent_sell_order_guard(state, order)
        if not recent_sell_allowed:
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=None,
                order=order,
                reason=recent_sell_reason,
                strategy_policy_summary=strategy_policy_summary,
            )
            state["execution"]["portfolio_guard"] = portfolio_details
            state["execution"]["recent_sell_order_guard"] = recent_sell_details
            _append_execution_trace_entries(
                state, order=order, execution=state["execution"], allow_result=None, strategy_policy_summary=strategy_policy_summary
            )
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="recent_sell_order_guard_block",
                payload={"allowed": False, "reason": recent_sell_reason, "portfolio_guard": portfolio_details, **recent_sell_details},
            )
            _persist_execution_artifacts(
                supervisor_allowed=False,
                supervisor_reason=recent_sell_reason,
                supervisor_details={**dict(portfolio_details or {}), **dict(recent_sell_details or {})},
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        cash_allowed, cash_reason, cash_details = _evaluate_mock_cash_guard(state, order)
        if not cash_allowed:
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=None,
                order=order,
                reason=cash_reason,
                strategy_policy_summary=strategy_policy_summary,
            )
            state["execution"]["cash_guard"] = cash_details
            state["execution"]["portfolio_guard"] = portfolio_details
            _append_execution_trace_entries(
                state, order=order, execution=state["execution"], allow_result=None, strategy_policy_summary=strategy_policy_summary
            )
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="verdict",
                payload={"allowed": False, "reason": cash_reason, "portfolio_guard": portfolio_details, **cash_details},
            )
            _persist_execution_artifacts(
                supervisor_allowed=False,
                supervisor_reason=cash_reason,
                supervisor_details={**dict(portfolio_details or {}), **dict(cash_details or {})},
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        degrade_allowed, degrade_reason, degrade_details = _evaluate_degrade_execution_policy(
            state=state,
            order=order,
            exec_context=exec_context,
        )
        if not degrade_allowed:
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=None,
                order=order,
                reason=degrade_reason,
                strategy_policy_summary=strategy_policy_summary,
            )
            state["execution"]["degrade_policy"] = degrade_details
            state["execution"]["portfolio_guard"] = portfolio_details
            _append_execution_trace_entries(
                state, order=order, execution=state["execution"], allow_result=None, strategy_policy_summary=strategy_policy_summary
            )
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="degrade_policy_block",
                payload={"reason": degrade_reason, "portfolio_guard": portfolio_details, **degrade_details},
            )
            _persist_execution_artifacts(
                supervisor_allowed=False,
                supervisor_reason=degrade_reason,
                supervisor_details={**dict(portfolio_details or {}), **dict(degrade_details or {})},
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        # Supervisor verdict
        allow_result = _supervisor_allow(supervisor, order, risk_for_supervisor)
        allowed = bool(getattr(allow_result, "allowed", getattr(allow_result, "allow", False)))
        # Mock mode bypasses supervisor gating for offline-safe test flows.
        # Real mode must honor supervisor verdict.
        if _resolve_execution_mode() == "mock":
            allowed = True

        if not allowed:
            state["execution"] = _normalize_execution(
                allowed=False,
                execution_result=None,
                allow_result=allow_result,
                order=order,
                reason=getattr(allow_result, "reason", "blocked"),
                strategy_policy_summary=strategy_policy_summary,
            )
            state["execution"]["portfolio_guard"] = portfolio_details
            allow_details = getattr(allow_result, "details", {})
            if isinstance(allow_details, dict) and allow_details:
                state["execution"]["supervisor_guard"] = dict(allow_details)
            _append_execution_trace_entries(
                state,
                order=order,
                execution=state["execution"],
                allow_result=allow_result,
                strategy_policy_summary=strategy_policy_summary,
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="verdict", payload=state["execution"])
            _persist_execution_artifacts(
                supervisor_allowed=False,
                supervisor_reason=getattr(allow_result, "reason", "blocked"),
                supervisor_details=allow_details if isinstance(allow_details, dict) else {},
            )
            logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
            return state

        # Prepare request and execute
        req = _prepare_request(order, catalog)
        execution_result = executor.execute(req)

        state["execution"] = _normalize_execution(
            allowed=True,
            execution_result=execution_result,
            allow_result=allow_result,
            order=order,
            strategy_policy_summary=strategy_policy_summary,
        )
        state["execution"]["portfolio_guard"] = portfolio_details
        allow_details = getattr(allow_result, "details", {})
        if isinstance(allow_details, dict) and allow_details:
            state["execution"]["supervisor_guard"] = dict(allow_details)
        recent_buy_guard_update = _update_recent_buy_order_guard(state, order, state["execution"])
        if bool(recent_buy_guard_update.get("enabled")):
            state["execution"]["recent_buy_order_guard"] = recent_buy_guard_update
        recent_sell_guard_update = _update_recent_sell_order_guard(state, order, state["execution"])
        if bool(recent_sell_guard_update.get("enabled")):
            state["execution"]["recent_sell_order_guard"] = recent_sell_guard_update

        _append_execution_trace_entries(
            state,
            order=order,
            execution=state["execution"],
            allow_result=allow_result,
            strategy_policy_summary=strategy_policy_summary,
        )
        logger.log(
            run_id=run_id,
            stage="execute_from_packet",
            event="verdict",
            payload={"allowed": True, "portfolio_guard": portfolio_details, "strategy_policy_summary": strategy_policy_summary},
        )
        upper_limit_cancel = _attempt_upper_limit_cancel(
            state=state,
            catalog=catalog,
            executor=executor,
            order=order,
            execution=state["execution"],
        )
        if upper_limit_cancel:
            state["execution"]["upper_limit_cancel"] = upper_limit_cancel
            logger.log(
                run_id=run_id,
                stage="execute_from_packet",
                event="upper_limit_cancel_attempt",
                payload=upper_limit_cancel,
            )
        logger.log(run_id=run_id, stage="execute_from_packet", event="execution", payload=state["execution"])
        _persist_execution_artifacts(
            supervisor_allowed=True,
            supervisor_reason=str(getattr(allow_result, "reason", "") or "allowed"),
            supervisor_details=allow_details if isinstance(allow_details, dict) else {},
        )
        logger.log(run_id=run_id, stage="execute_from_packet", event="end", payload={"ok": True})
        return state

    except Exception as e:
        state["execution"] = {"allowed": False, "reason": str(e)}
        if strategy_policy_summary:
            state["execution"]["strategy_policy_summary"] = dict(strategy_policy_summary)
        _append_execution_trace_entries(
            state,
            order=order,
            execution=state["execution"],
            allow_result=allow_result,
            strategy_policy_summary=strategy_policy_summary,
        )
        _persist_execution_artifacts(
            supervisor_allowed=False,
            supervisor_reason=str(e),
            supervisor_details={},
        )
        logger.log(run_id=run_id, stage="execute_from_packet", event="error", payload={"error": str(e)})
        raise
