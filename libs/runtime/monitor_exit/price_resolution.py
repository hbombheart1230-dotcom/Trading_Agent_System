from __future__ import annotations

from typing import Any, Dict

from graphs.nodes.skill_contracts import extract_market_quotes, extract_minute_ohlcv_by_symbol
from libs.core.symbols import normalize_symbol
from libs.runtime.monitor_exit.numeric import to_float


def _to_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def resolve_price(
    state: Dict[str, Any],
    symbol: str,
    selected: Dict[str, Any] | None,
    *,
    position: Dict[str, Any] | None = None,
) -> float | None:
    price, _source = resolve_price_with_source(state, symbol, selected, position=position)
    return price


def resolve_price_with_source(
    state: Dict[str, Any],
    symbol: str,
    selected: Dict[str, Any] | None,
    *,
    position: Dict[str, Any] | None = None,
) -> tuple[float | None, str]:
    sym = normalize_symbol(symbol)
    if not sym:
        return None, "no_symbol"

    quotes, _meta = extract_market_quotes(state)
    quote = quotes.get(sym)
    if isinstance(quote, dict):
        for key in ("price", "cur"):
            if quote.get(key) is not None:
                price = to_float(quote.get(key))
                if price > 0.0:
                    return price, f"market.quote.{key}"

    if isinstance(position, dict):
        pos_live_price, pos_live_source = position_live_price_with_source(
            position, requested_symbol=sym
        )
        if pos_live_price is not None and pos_live_price > 0.0:
            return pos_live_price, pos_live_source

    selected_symbol = normalize_symbol((selected or {}).get("symbol")) if isinstance(selected, dict) else ""
    selected_matches = bool(selected_symbol and selected_symbol == sym)
    if isinstance(selected, dict) and selected_matches:
        direct = selected.get("price")
        if direct is not None:
            price = to_float(direct)
            if price > 0.0:
                source_hint = str(selected.get("_monitor_price_source") or "").strip()
                return price, (source_hint or "selected.price")
        features = selected.get("features")
        if isinstance(features, dict):
            feature_price = features.get("skill_quote_price")
            if feature_price is not None:
                price = to_float(feature_price)
                if price > 0.0:
                    source_hint = str(selected.get("_monitor_price_source") or "").strip()
                    return price, (source_hint or "selected.features.skill_quote_price")

    market_snapshot = state.get("market_snapshot")
    if isinstance(market_snapshot, dict):
        market_symbol = normalize_symbol(market_snapshot.get("symbol"))
        snapshot_price = market_snapshot.get("price")
        if market_symbol == sym and snapshot_price is not None:
            price = to_float(snapshot_price)
            if price > 0.0:
                return price, "market_snapshot"

    minute_rows_by_symbol, minute_meta = extract_minute_ohlcv_by_symbol(state)
    minute_rows = minute_rows_by_symbol.get(sym) if isinstance(minute_rows_by_symbol, dict) else None
    if isinstance(minute_rows, list) and minute_rows:
        latest = minute_rows[-1] if isinstance(minute_rows[-1], dict) else {}
        close_price = to_float(latest.get("close"))
        if close_price > 0.0:
            source = str((minute_meta or {}).get("source") or "minute_ohlcv_by_symbol").strip() or "minute_ohlcv_by_symbol"
            return close_price, f"{source}.close"
    return None, "unavailable"


def quote_observed_epoch(quote: Dict[str, Any] | None) -> int | None:
    if not isinstance(quote, dict):
        return None
    for key in ("_observed_epoch", "observed_epoch"):
        value = quote.get(key)
        try:
            epoch = int(float(value))
        except Exception:
            continue
        if epoch > 0:
            return epoch
    return None


def position_mark_price(position: Dict[str, Any] | None) -> float | None:
    price, _source = position_mark_price_with_source(position)
    return price


def position_live_price_with_source(
    position: Dict[str, Any] | None,
    *,
    requested_symbol: str = "",
) -> tuple[float | None, str]:
    if not isinstance(position, dict):
        return None, "no_position"
    requested = normalize_symbol(requested_symbol)
    position_symbol = normalize_symbol(
        position.get("symbol") or position.get("stk_cd") or position.get("code")
    )
    if requested and position_symbol and requested != position_symbol:
        return None, "position_symbol_mismatch"
    for key in ("price", "cur_price", "last_price", "current_price"):
        price = to_float(position.get(key))
        if price > 0.0:
            return price, f"position.{key}"
    return None, "position_live_price_unavailable"


def position_mark_price_with_source(position: Dict[str, Any] | None) -> tuple[float | None, str]:
    direct_price, direct_source = position_live_price_with_source(position)
    if direct_price is not None and direct_price > 0.0:
        return direct_price, direct_source
    if not isinstance(position, dict):
        return None, "no_position"
    qty = max(0, _to_int(position.get("qty")))
    avg_price = to_float(position.get("avg_price"))
    unrealized = to_float(position.get("unrealized_pnl"))
    if qty > 0 and avg_price > 0.0:
        mark = avg_price + (unrealized / float(qty))
        if mark > 0.0:
            return mark, "position.avg_plus_unrealized"
    return None, "position_mark_unavailable"
