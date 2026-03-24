from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from libs.core.symbols import normalize_symbol
from .dto import QuoteDTO, MinuteOHLCVDTO, OrderPlaceDTO, OrderStatusDTO, AccountOrdersDTO, RawDTO


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
    normalized = normalize_symbol(code)
    return normalized or None


_KST = timezone(timedelta(hours=9))


def _to_abs_int(v: Any) -> Optional[int]:
    parsed = _to_int(v)
    if parsed is None:
        return None
    return abs(parsed)


def _parse_kst_timestamp(value: Any) -> Optional[int]:
    raw = str(value or "").strip()
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) >= 14:
        digits = digits[:14]
        try:
            dt = datetime.strptime(digits, "%Y%m%d%H%M%S").replace(tzinfo=_KST)
            return int(dt.timestamp())
        except Exception:
            return None
    if len(digits) == 6:
        today = datetime.now(_KST).strftime("%Y%m%d")
        try:
            dt = datetime.strptime(today + digits, "%Y%m%d%H%M%S").replace(tzinfo=_KST)
            return int(dt.timestamp())
        except Exception:
            return None
    return None


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


def extract_minute_ohlcv(symbol: str, timeframe_minutes: int, payload: Dict[str, Any]) -> MinuteOHLCVDTO:
    rows = payload.get("stk_min_pole_chart_qry")
    if not isinstance(rows, list):
        rows = payload.get("items")
    if not isinstance(rows, list):
        rows = payload.get("data")
    if not isinstance(rows, list):
        rows = []

    normalized_rows: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        close_px = _to_abs_int(row.get("cur_prc"))
        open_px = _to_abs_int(row.get("open_pric"))
        high_px = _to_abs_int(row.get("high_pric"))
        low_px = _to_abs_int(row.get("low_pric"))
        volume = _to_abs_int(row.get("trde_qty")) or _to_abs_int(row.get("acc_trde_qty"))
        if close_px is None and open_px is None and high_px is None and low_px is None:
            continue
        price_fallback = close_px or open_px or high_px or low_px
        if price_fallback is None or price_fallback <= 0:
            continue
        ts = _parse_kst_timestamp(row.get("cntr_tm") or row.get("tm") or row.get("dt"))
        normalized_rows.append(
            {
                "ts": int(ts) if ts else None,
                "open": float(open_px or price_fallback),
                "high": float(high_px or max(open_px or price_fallback, close_px or price_fallback)),
                "low": float(low_px or min(open_px or price_fallback, close_px or price_fallback)),
                "close": float(close_px or price_fallback),
                "volume": float(max(0, volume or 0)),
                "raw_ts": row.get("cntr_tm") or row.get("tm") or row.get("dt"),
            }
        )

    normalized_rows.sort(
        key=lambda item: (
            0 if item.get("ts") is not None else 1,
            int(item.get("ts") or 0),
            str(item.get("raw_ts") or ""),
        )
    )
    return MinuteOHLCVDTO(
        symbol=symbol,
        timeframe_minutes=max(1, int(timeframe_minutes or 1)),
        rows=normalized_rows,
        raw=payload,
    )


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
