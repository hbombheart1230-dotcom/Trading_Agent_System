from __future__ import annotations

from typing import Any, Dict, List, Mapping

from libs.core.symbols import normalize_symbol


def _safe_float(value: Any, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int | None = None) -> int | None:
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except Exception:
        return default


def build_split_fill_match_payload(
    rows: List[Mapping[str, Any]],
    *,
    symbol: str,
    row_count: int,
    match_mode: str,
    filled_qty: int,
    filled_price: float | None,
    buy_price: float | None,
    source: str = "kiwoom.ka10077",
) -> Dict[str, Any]:
    realized_values = [_safe_float(row.get("realized_pnl")) for row in rows]
    fee_values = [_safe_int(row.get("fee")) for row in rows]
    tax_values = [_safe_int(row.get("tax")) for row in rows]
    realized_pnl = sum(float(value) for value in realized_values if value is not None)
    fee = sum(int(value) for value in fee_values if value is not None)
    tax = sum(int(value) for value in tax_values if value is not None)
    pnl_ratio = None
    if buy_price not in (None, 0) and filled_qty not in (None, 0):
        try:
            pnl_ratio = float(realized_pnl) / (float(buy_price) * float(filled_qty))
        except Exception:
            pnl_ratio = None
    return {
        "symbol": normalize_symbol(symbol, allow_test_symbols=True),
        "filled_qty": int(filled_qty),
        "filled_price": filled_price,
        "buy_price": buy_price,
        "realized_pnl": float(realized_pnl),
        "pnl_ratio": pnl_ratio,
        "fee": int(fee),
        "tax": int(tax),
        "source": str(source or "kiwoom.ka10077"),
        "match_mode": str(match_mode or ""),
        "row_count": int(row_count),
        "source_row_count": int(len(rows)),
        "authoritative": True,
    }
