from __future__ import annotations

from typing import Any, Dict, List

from graphs.nodes.skill_contracts import extract_market_quotes, extract_minute_ohlcv_by_symbol
from libs.core.symbols import normalize_symbol
from libs.runtime.monitor_exit.numeric import to_float


def quote_for_symbol(state: Dict[str, Any], symbol: str) -> Dict[str, Any]:
    sym = normalize_symbol(symbol)
    quotes, _quote_meta = extract_market_quotes(state)
    quote = quotes.get(sym) if isinstance(quotes.get(sym), dict) else {}
    return dict(quote or {})


def minute_rows_for_symbol(state: Dict[str, Any], symbol: str) -> tuple[List[Dict[str, Any]] | None, str]:
    sym = normalize_symbol(symbol)
    if not sym:
        return None, ""
    minute_rows_by_symbol, minute_meta = extract_minute_ohlcv_by_symbol(state)
    rows = minute_rows_by_symbol.get(sym) if isinstance(minute_rows_by_symbol, dict) else None
    source = str((minute_meta or {}).get("source") or "minute_ohlcv_by_symbol").strip() or "minute_ohlcv_by_symbol"
    if not isinstance(rows, list) or not rows:
        return None, source
    return [row for row in rows if isinstance(row, dict)], source


def fresh_minute_vwap_distance_for_symbol(
    state: Dict[str, Any],
    symbol: str,
    *,
    price: float | None = None,
) -> tuple[float | None, str]:
    rows, source = minute_rows_for_symbol(state, symbol)
    if not normalize_symbol(symbol):
        return None, "no_symbol"
    if not rows:
        return None, "minute_vwap_unavailable"
    latest = rows[-1] if isinstance(rows[-1], dict) else {}
    current_vwap = to_float(latest.get("vwap"))
    current_price = to_float(price)
    if current_price <= 0.0:
        current_price = to_float(latest.get("close"))
    if current_vwap <= 0.0 or current_price <= 0.0:
        return None, "minute_vwap_or_price_unavailable"
    return float((current_price - current_vwap) / current_vwap), f"{source}.vwap_distance"

