from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .dto import QuoteDTO, OrderPlaceDTO, OrderStatusDTO, AccountOrdersDTO, RawDTO


def _to_int(v: Any) -> Optional[int]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "").lstrip("+")
        if not s:
            return None
        try:
            return int(float(s))
        except Exception:
            return None
    return None


def _norm_symbol(code: Optional[str]) -> Optional[str]:
    if not code:
        return code
    code = str(code)
    if code.startswith("A") and len(code) > 1:
        return code[1:]
    return code


def extract_quote(symbol: str, payload: Dict[str, Any]) -> QuoteDTO:
    items = None
    for k in ("cntr_infr", "items", "data", "result"):
        if isinstance(payload.get(k), list):
            items = payload.get(k)
            break
    cur = best_bid = best_ask = None
    if items:
        r = items[0] or {}
        cur = _to_int(r.get("cur_prc"))
        best_ask = _to_int(r.get("pri_sel_bid_unit"))
        best_bid = _to_int(r.get("pri_buy_bid_unit"))
    return QuoteDTO(symbol=symbol, cur=cur, best_bid=best_bid, best_ask=best_ask, raw=payload)


def extract_order_place(side: str, symbol: str, payload: Dict[str, Any]) -> OrderPlaceDTO:
    ord_no = payload.get("ord_no")
    msg = str(payload.get("return_msg") or "")
    return OrderPlaceDTO(side=side, symbol=symbol, ord_no=str(ord_no) if ord_no else None, message=msg, raw=payload)


def extract_order_status(ord_no: str, payloads: List[Dict[str, Any]]) -> OrderStatusDTO:
    # We rely on kt00007 detail row primarily
    row: Dict[str, Any] = {}
    for p in payloads:
        rows = p.get("acnt_ord_cntr_prps_dtl")
        if isinstance(rows, list):
            for r in rows:
                if str(r.get("ord_no", "")).strip() == ord_no:
                    row = r
                    break
        if row:
            break

    symbol = _norm_symbol(row.get("stk_cd")) if row else None
    status = row.get("acpt_tp") if row else None
    filled_qty = _to_int(row.get("cntr_qty")) if row else None
    filled_price = _to_int(row.get("cntr_uv")) if row else None
    order_qty = _to_int(row.get("ord_qty")) if row else None
    order_price = _to_int(row.get("ord_uv")) if row else None
    side = row.get("io_tp_nm") if row else None

    merged_raw = {"payloads": payloads, "matched": row}
    return OrderStatusDTO(
        ord_no=ord_no,
        symbol=symbol,
        status=str(status) if status is not None else None,
        filled_qty=filled_qty,
        filled_price=filled_price,
        order_qty=order_qty,
        order_price=order_price,
        side=str(side) if side is not None else None,
        raw=merged_raw,
    )


def extract_account_orders(payload: Dict[str, Any]) -> AccountOrdersDTO:
    rows = payload.get("acnt_ord_cntr_prps_dtl")
    if not isinstance(rows, list):
        rows = []
    return AccountOrdersDTO(rows=rows, raw=payload)


def as_raw(payloads: List[Dict[str, Any]], meta: Dict[str, Any]) -> RawDTO:
    ok = True
    for p in payloads:
        rc = p.get("return_code")
        if rc not in (0, "0", None):
            ok = False
    return RawDTO(ok=ok, payloads=payloads, meta=meta)
