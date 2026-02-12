from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ParsedIntent:
    action: str  # BUY/SELL/QUOTE/STATUS/APPROVE/UNKNOWN
    symbol: Optional[str] = None
    qty: Optional[int] = None
    price: Optional[int] = None
    order_type: Optional[str] = None  # market/limit
    ord_no: Optional[str] = None
    ord_dt: Optional[str] = None  # YYYYMMDD
    qry_tp: Optional[str] = None
    mrkt_tp: Optional[str] = None
    intent_id: Optional[str] = None


_SYMBOL_RE = re.compile(r"\b(\d{6})\b")
_ORDNO_RE = re.compile(r"\b(\d{7})\b")
_DATE_RE = re.compile(r"\b(20\d{6})\b")  # YYYYMMDD
_INTENTID_RE = re.compile(r"\b([0-9a-f]{32})\b", re.IGNORECASE)


def parse_nl(text: str) -> ParsedIntent:
    t = (text or "").strip()
    low = t.lower()

    # approval command: "승인 <intent_id>" or "approve <intent_id>"
    if "승인" in t or "approve" in low:
        m = _INTENTID_RE.search(t)
        return ParsedIntent(action="APPROVE", intent_id=m.group(1) if m else None)

    symbol = None
    m = _SYMBOL_RE.search(t)
    if m:
        symbol = m.group(1)

    ord_no = None
    m2 = _ORDNO_RE.search(t)
    if m2:
        ord_no = m2.group(1)

    ord_dt = None
    m3 = _DATE_RE.search(t)
    if m3:
        ord_dt = m3.group(1)

    qty = None
    m4 = re.search(r"(\d+)\s*주", t)
    if m4:
        qty = int(m4.group(1))
    else:
        m4 = re.search(r"\bqty\s*(\d+)\b", low)
        if m4:
            qty = int(m4.group(1))

    price = None
    m5 = re.search(r"(\d{3,})\s*원", t)
    if m5:
        price = int(m5.group(1))
    else:
        m5 = re.search(r"(?:가격|price)\s*(\d{3,})", low)
        if m5:
            price = int(m5.group(1))

    order_type = None
    if "시장가" in t or "market" in low:
        order_type = "market"
    if "지정가" in t or "limit" in low:
        order_type = "limit"

    if any(k in t for k in ["현재가", "호가", "시세", "quote"]):
        return ParsedIntent(action="QUOTE", symbol=symbol)

    if any(k in t for k in ["주문조회", "체결조회", "order status", "status"]):
        return ParsedIntent(action="STATUS", symbol=symbol, ord_no=ord_no, ord_dt=ord_dt, qry_tp="3", mrkt_tp="0")

    if any(k in t for k in ["매수", "buy"]):
        return ParsedIntent(action="BUY", symbol=symbol, qty=qty, price=price, order_type=order_type or "market")

    if any(k in t for k in ["매도", "sell"]):
        return ParsedIntent(action="SELL", symbol=symbol, qty=qty, price=price, order_type=order_type or "market")

    return ParsedIntent(action="UNKNOWN", symbol=symbol, qty=qty, price=price, order_type=order_type, ord_no=ord_no, ord_dt=ord_dt)
