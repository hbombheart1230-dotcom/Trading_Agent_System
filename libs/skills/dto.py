from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class RawDTO:
    ok: bool
    payloads: List[Dict[str, Any]]
    meta: Dict[str, Any]


@dataclass(frozen=True)
class QuoteDTO:
    symbol: str
    cur: Optional[int]
    best_bid: Optional[int]
    best_ask: Optional[int]
    raw: Dict[str, Any]


@dataclass(frozen=True)
class OrderPlaceDTO:
    side: str
    symbol: str
    ord_no: Optional[str]
    message: str
    raw: Dict[str, Any]


@dataclass(frozen=True)
class OrderStatusDTO:
    ord_no: str
    symbol: Optional[str]
    status: Optional[str]
    filled_qty: Optional[int]
    filled_price: Optional[int]
    order_qty: Optional[int]
    order_price: Optional[int]
    side: Optional[str]
    raw: Dict[str, Any]


@dataclass(frozen=True)
class AccountOrdersDTO:
    rows: List[Dict[str, Any]]
    raw: Dict[str, Any]
