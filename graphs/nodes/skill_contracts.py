from __future__ import annotations

from typing import Any, Dict, List, Tuple

from libs.core.symbols import normalize_symbol


CONTRACT_VERSION = "m22.skill.v1"


def norm_symbol(v: Any) -> str:
    return normalize_symbol(v)


def _get_skill_root(state: Dict[str, Any]) -> Dict[str, Any]:
    for k in ("skill_results", "skill_data", "skills"):
        v = state.get(k)
        if isinstance(v, dict):
            return v
    return {}


def _pick_skill_value(
    state: Dict[str, Any],
    keys: Tuple[str, ...],
    *,
    state_key: str | None = None,
) -> Tuple[Any, bool]:
    root = _get_skill_root(state)
    for k in keys:
        if k in root:
            return root.get(k), True
    if state_key and state_key in state:
        return state.get(state_key), True
    return None, False


def _unwrap_skill_payload(raw: Any, *, skill_name: str) -> Tuple[Any, List[str]]:
    errors: List[str] = []
    if raw is None:
        return None, errors

    if isinstance(raw, dict):
        action = str(raw.get("action") or "").strip().lower()
        if action in ("error", "ask"):
            meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
            error_type = str(
                meta.get("error_type")
                or raw.get("error_type")
                or raw.get("reason")
                or raw.get("question")
                or "skill_not_ready"
            )
            errors.append(f"{skill_name}:{action}:{error_type}")
            return None, errors

        if raw.get("ok") is False:
            error_type = str(raw.get("error_type") or raw.get("reason") or "skill_error")
            errors.append(f"{skill_name}:error:{error_type}")
            return None, errors

        if isinstance(raw.get("result"), dict):
            result = raw.get("result") or {}
            result_action = str(result.get("action") or "").strip().lower()
            if result_action in ("error", "ask"):
                meta = result.get("meta") if isinstance(result.get("meta"), dict) else {}
                error_type = str(
                    meta.get("error_type")
                    or result.get("error_type")
                    or result.get("reason")
                    or result.get("question")
                    or "skill_not_ready"
                )
                errors.append(f"{skill_name}:{result_action}:{error_type}")
                return None, errors
            if "data" in result:
                return result.get("data"), errors

        if "data" in raw:
            return raw.get("data"), errors

    return raw, errors


def _meta(*, present: bool, used: bool, errors: List[str]) -> Dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "present": bool(present),
        "used": bool(used),
        "errors": list(errors),
    }


def extract_market_quotes(state: Dict[str, Any]) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    raw, present = _pick_skill_value(state, ("market.quote", "market_quote"), state_key="market_quote")
    unwrapped, errors = _unwrap_skill_payload(raw, skill_name="market.quote")
    out: Dict[str, Dict[str, Any]] = {}

    def _save(sym: Any, rec: Dict[str, Any]) -> None:
        key = norm_symbol(sym)
        if not key:
            return
        row = dict(rec)
        row["symbol"] = key
        if row.get("price") is None and row.get("cur") is not None:
            row["price"] = row.get("cur")
        out[key] = row

    if isinstance(unwrapped, dict):
        if unwrapped.get("symbol") is not None and any(k in unwrapped for k in ("cur", "price", "best_bid", "best_ask")):
            _save(unwrapped.get("symbol"), unwrapped)
        else:
            for k, v in unwrapped.items():
                if not isinstance(v, dict):
                    continue
                if not any(x in v for x in ("cur", "price", "best_bid", "best_ask")):
                    continue
                _save(v.get("symbol") or k, v)
    elif isinstance(unwrapped, list):
        for row in unwrapped:
            if not isinstance(row, dict):
                continue
            if row.get("symbol") is None:
                continue
            _save(row.get("symbol"), row)

    if present and not out and not errors:
        errors.append("market.quote:contract_violation")
    return out, _meta(present=present, used=bool(out), errors=errors)


def _normalize_ohlcv_row(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    if "symbol" in out:
        out.pop("symbol", None)
    return out


def _save_ohlcv_rows(out: Dict[str, List[Dict[str, Any]]], symbol: Any, rows: Any) -> bool:
    key = norm_symbol(symbol)
    if not key or not isinstance(rows, list):
        return False
    normalized: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        normalized.append(_normalize_ohlcv_row(row))
    if not normalized:
        return False
    out[key] = normalized
    return True


def extract_minute_ohlcv_by_symbol(state: Dict[str, Any]) -> Tuple[Dict[str, List[Dict[str, Any]]], Dict[str, Any]]:
    """Resolve monitor-only minute OHLCV contract.

    This intentionally does not read `ohlcv_by_symbol`, which remains the
    scanner/feature seed store and may contain daily candles.
    """
    direct_present = False
    out: Dict[str, List[Dict[str, Any]]] = {}
    for state_key in ("minute_ohlcv_by_symbol", "monitor_minute_ohlcv_by_symbol", "intraday_ohlcv_by_symbol"):
        raw = state.get(state_key)
        if not isinstance(raw, dict):
            continue
        direct_present = True
        for symbol, rows in raw.items():
            _save_ohlcv_rows(out, symbol, rows)
        if out:
            return out, {
                "contract_version": CONTRACT_VERSION,
                "present": True,
                "used": True,
                "errors": [],
                "source": f"state.{state_key}",
            }

    skill_results = state.get("skill_results") if isinstance(state.get("skill_results"), dict) else {}
    per_symbol_results = (
        skill_results.get("market.minute_ohlcv_by_symbol")
        if isinstance(skill_results, dict) and isinstance(skill_results.get("market.minute_ohlcv_by_symbol"), dict)
        else {}
    )
    if isinstance(per_symbol_results, dict) and per_symbol_results:
        errors: List[str] = []
        for symbol, raw_value in per_symbol_results.items():
            unwrapped, raw_errors = _unwrap_skill_payload(raw_value, skill_name="market.minute_ohlcv")
            errors.extend(list(raw_errors or []))
            if isinstance(unwrapped, dict):
                if isinstance(unwrapped.get("symbol"), (str, int)) and isinstance(unwrapped.get("rows"), list):
                    _save_ohlcv_rows(out, unwrapped.get("symbol"), unwrapped.get("rows"))
                else:
                    for nested_symbol, rows in unwrapped.items():
                        _save_ohlcv_rows(out, nested_symbol, rows)
            elif isinstance(unwrapped, list):
                _save_ohlcv_rows(out, symbol, unwrapped)
        if out:
            return out, {
                "contract_version": CONTRACT_VERSION,
                "present": True,
                "used": True,
                "errors": list(errors),
                "source": "skill.minute_ohlcv_by_symbol",
            }

    raw, present = _pick_skill_value(
        state,
        ("market.minute_ohlcv", "market.minute_candles", "market.candles"),
        state_key="minute_ohlcv",
    )
    unwrapped, errors = _unwrap_skill_payload(raw, skill_name="market.minute_ohlcv")

    if isinstance(unwrapped, dict):
        if isinstance(unwrapped.get("symbol"), (str, int)) and isinstance(unwrapped.get("rows"), list):
            _save_ohlcv_rows(out, unwrapped.get("symbol"), unwrapped.get("rows"))
        else:
            for symbol, rows in unwrapped.items():
                _save_ohlcv_rows(out, symbol, rows)
    elif isinstance(unwrapped, list):
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in unwrapped:
            if not isinstance(row, dict):
                continue
            symbol = norm_symbol(row.get("symbol"))
            if not symbol:
                continue
            grouped.setdefault(symbol, []).append(_normalize_ohlcv_row(row))
        out.update(grouped)

    present_flag = bool(direct_present or present)
    if present_flag and not out and not errors:
        errors.append("market.minute_ohlcv:contract_violation")
    return out, {
        "contract_version": CONTRACT_VERSION,
        "present": present_flag,
        "used": bool(out),
        "errors": list(errors),
        "source": "skill.minute_ohlcv" if bool(out) and not direct_present else ("none" if not present_flag else "state"),
    }


def extract_account_orders_rows(state: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    raw, present = _pick_skill_value(state, ("account.orders", "account_orders"), state_key="account_orders")
    unwrapped, errors = _unwrap_skill_payload(raw, skill_name="account.orders")
    rows: List[Dict[str, Any]] = []

    if isinstance(unwrapped, dict):
        if isinstance(unwrapped.get("rows"), list):
            rows = [x for x in (unwrapped.get("rows") or []) if isinstance(x, dict)]
        elif isinstance(unwrapped.get("acnt_ord_cntr_prps_dtl"), list):
            rows = [x for x in (unwrapped.get("acnt_ord_cntr_prps_dtl") or []) if isinstance(x, dict)]
        elif isinstance(unwrapped.get("items"), list):
            rows = [x for x in (unwrapped.get("items") or []) if isinstance(x, dict)]
    elif isinstance(unwrapped, list):
        rows = [x for x in unwrapped if isinstance(x, dict)]

    if present and not rows and not errors:
        errors.append("account.orders:contract_violation")
    return rows, _meta(present=present, used=bool(rows), errors=errors)


def extract_order_status(state: Dict[str, Any]) -> Tuple[Dict[str, Any] | None, Dict[str, Any]]:
    raw, present = _pick_skill_value(state, ("order.status", "order_status"), state_key="order_status")
    unwrapped, errors = _unwrap_skill_payload(raw, skill_name="order.status")
    if not isinstance(unwrapped, dict):
        if present and not errors:
            errors.append("order.status:contract_violation")
        return None, _meta(present=present, used=False, errors=errors)

    row = dict(unwrapped)
    if isinstance(row.get("result"), dict):
        data = row.get("result", {}).get("data")
        if isinstance(data, dict):
            row = dict(data)

    symbol = norm_symbol(row.get("symbol") or row.get("stk_cd"))
    summary = {
        "ord_no": row.get("ord_no"),
        "symbol": symbol or None,
        "status": row.get("status") or row.get("acpt_tp"),
        "filled_qty": row.get("filled_qty") or row.get("cntr_qty"),
        "order_qty": row.get("order_qty") or row.get("ord_qty"),
        "filled_price": row.get("filled_price") or row.get("cntr_uv"),
        "order_price": row.get("order_price") or row.get("ord_uv"),
    }
    return summary, _meta(present=present, used=True, errors=errors)
