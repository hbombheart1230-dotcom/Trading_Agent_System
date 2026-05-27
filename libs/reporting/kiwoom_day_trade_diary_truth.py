from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from libs.core.symbols import normalize_symbol


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except Exception:
        return default


def _price_matches(left: Any, right: Any) -> bool:
    left_value = _safe_float(left)
    right_value = _safe_float(right)
    if left_value is None or right_value is None:
        return False
    return abs(left_value - right_value) < 0.5


def _build_match(row: Mapping[str, Any], *, symbol: str, row_count: int, match_mode: str) -> Dict[str, Any]:
    fee_tax = _safe_int(row.get("fee_tax"))
    return {
        "symbol": normalize_symbol(symbol, allow_test_symbols=True),
        "filled_qty": _safe_int(row.get("sell_qty")),
        "filled_price": _safe_float(row.get("sell_avg_price")),
        "buy_price": _safe_float(row.get("buy_avg_price")),
        "realized_pnl": _safe_float(row.get("realized_pnl")),
        "pnl_ratio": _safe_float(row.get("pnl_ratio")),
        "fee": fee_tax,
        "tax": None,
        "fee_tax": fee_tax,
        "source": "kiwoom.ka10170",
        "match_mode": match_mode,
        "row_count": int(row_count),
        "authoritative": True,
    }


def match_trade_diary_row(
    rows: List[Dict[str, Any]],
    *,
    symbol: str,
    filled_qty: Any = None,
    filled_price: Any = None,
    buy_price: Any = None,
) -> Dict[str, Any]:
    normalized_symbol = normalize_symbol(symbol, allow_test_symbols=True)
    symbol_rows = [
        dict(row)
        for row in list(rows or [])
        if normalize_symbol((row or {}).get("symbol"), allow_test_symbols=True) == normalized_symbol
    ]
    row_count = len(symbol_rows)
    if not row_count:
        return {}

    qty_value = _safe_int(filled_qty)
    sell_price_value = _safe_float(filled_price)
    buy_price_value = _safe_float(buy_price)

    predicates = [
        (
            "ka10170_symbol_buy_sell_qty_exact",
            lambda row: qty_value is not None
            and buy_price_value is not None
            and _safe_int(row.get("sell_qty")) == qty_value
            and _price_matches(row.get("sell_avg_price"), sell_price_value)
            and _price_matches(row.get("buy_avg_price"), buy_price_value),
        ),
        (
            "ka10170_symbol_qty_sell_price_exact",
            lambda row: qty_value is not None
            and _safe_int(row.get("sell_qty")) == qty_value
            and _price_matches(row.get("sell_avg_price"), sell_price_value),
        ),
        (
            "ka10170_symbol_qty_exact",
            lambda row: qty_value is not None and _safe_int(row.get("sell_qty")) == qty_value,
        ),
    ]
    for match_mode, predicate in predicates:
        matches = [row for row in symbol_rows if predicate(row)]
        if len(matches) == 1:
            return _build_match(matches[0], symbol=normalized_symbol, row_count=row_count, match_mode=match_mode)

    if row_count == 1:
        return _build_match(symbol_rows[0], symbol=normalized_symbol, row_count=row_count, match_mode="ka10170_single_symbol_row")

    return {
        "symbol": normalized_symbol,
        "source": "kiwoom.ka10170",
        "match_mode": "ka10170_ambiguous_symbol_rows",
        "row_count": row_count,
        "authoritative": False,
    }


__all__ = ["match_trade_diary_row"]
