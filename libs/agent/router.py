from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .intent_parser import ParsedIntent


@dataclass(frozen=True)
class RoutedCall:
    tool: str
    kwargs: Dict[str, Any]


def route(intent: ParsedIntent) -> RoutedCall:
    a = intent.action

    if a == "QUOTE":
        return RoutedCall(tool="market_quote", kwargs={"symbol": intent.symbol})

    if a in ("BUY", "SELL"):
        return RoutedCall(
            tool="order_place_intent",
            kwargs={
                "side": "buy" if a == "BUY" else "sell",
                "symbol": intent.symbol,
                "qty": intent.qty or 1,
                "order_type": intent.order_type or "market",
                "price": intent.price,
            },
        )

    if a == "STATUS":
        return RoutedCall(
            tool="order_status",
            kwargs={
                "ord_no": intent.ord_no,
                "symbol": intent.symbol,
                "ord_dt": intent.ord_dt,
                "qry_tp": intent.qry_tp or "3",
                "mrkt_tp": intent.mrkt_tp or "0",
            },
        )

    if a == "APPROVE":
        return RoutedCall(tool="approve_intent", kwargs={"intent_id": intent.intent_id})

    return RoutedCall(tool="help", kwargs={"query": "지원하지 않는 요청입니다."})
