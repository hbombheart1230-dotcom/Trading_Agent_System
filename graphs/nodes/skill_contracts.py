from __future__ import annotations

from typing import Any, Dict, List, Tuple


CONTRACT_VERSION = "m22.skill.v1"


def norm_symbol(v: Any) -> str:
    s = str(v or "").strip()
    if s.startswith("A") and len(s) > 1 and s[1:].isdigit():
        return s[1:]
    return s


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
