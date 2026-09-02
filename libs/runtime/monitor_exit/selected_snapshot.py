from __future__ import annotations

from typing import Any, Dict

from graphs.nodes.skill_contracts import extract_market_quotes
from libs.core.symbols import normalize_symbol
from libs.runtime.feature_engine import build_feature_row
from libs.runtime.monitor_exit.numeric import to_float
from libs.runtime.monitor_exit.price_resolution import quote_observed_epoch, resolve_price_with_source


def feature_alias_map(feature_row: Dict[str, Any], *, quote: Dict[str, Any] | None = None) -> Dict[str, Any]:
    row = dict(feature_row or {})
    quote_row = dict(quote or {})
    out = {
        "engine_rsi14": row.get("engine_rsi14", row.get("rsi14")),
        "engine_ma20_gap": row.get("engine_ma20_gap", row.get("ma20_gap")),
        "engine_ma60": row.get("engine_ma60", row.get("ma60")),
        "engine_ma120": row.get("engine_ma120", row.get("ma120")),
        "engine_adx14": row.get("engine_adx14", row.get("adx14")),
        "engine_trend_strength": row.get("engine_trend_strength", row.get("trend_strength")),
        "engine_atr14": row.get("engine_atr14", row.get("atr14")),
        "engine_volume_spike20": row.get("engine_volume_spike20", row.get("volume_spike20")),
        "engine_volatility20": row.get("engine_volatility20", row.get("volatility20")),
        "engine_realized_volatility": row.get("engine_realized_volatility", row.get("realized_volatility")),
        "engine_vwap_distance": row.get("engine_vwap_distance", row.get("vwap_distance")),
        "engine_rolling_drawdown20": row.get("engine_rolling_drawdown20", row.get("rolling_drawdown20")),
        "engine_cross_section_rank": row.get("engine_cross_section_rank", row.get("cross_section_rank")),
        "engine_regime": row.get("engine_regime", row.get("regime")),
        "engine_signal_score": row.get("engine_signal_score", row.get("signal_score")),
        "volume_ratio": row.get("volume_ratio", row.get("engine_volume_ratio")),
        "execution_strength": row.get("execution_strength", row.get("trade_strength")),
        "trade_strength": row.get("trade_strength"),
        "previous_close": row.get("previous_close"),
        "open_gap_pct": row.get("open_gap_pct"),
        "prev_close_distance_pct": row.get("prev_close_distance_pct"),
        "opening_gap_chase_observed": row.get("opening_gap_chase_observed"),
        "minutes_since_session_open": row.get("minutes_since_session_open"),
        "recent_high": row.get("recent_high"),
        "breakout_level": row.get("breakout_level"),
        "prior_bar_high": row.get("prior_bar_high"),
        "day_high": row.get("day_high", row.get("high_price")),
        "intraday_high": row.get("intraday_high"),
        "resistance_price": row.get("resistance_price"),
        "target_resistance_price": row.get("target_resistance_price"),
        "upper_resistance_price": row.get("upper_resistance_price"),
    }
    if quote_row:
        quote_price = quote_row.get("price")
        if quote_price is None:
            quote_price = quote_row.get("cur")
        out["skill_quote_price"] = quote_price
        out["intraday_change_pct"] = quote_row.get("change_pct")
        out["quote_volume"] = quote_row.get("volume")
        out["quote_trading_value"] = quote_row.get("value")
    return out


def feature_context_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    market_ctx = state.get("market_context") if isinstance(state.get("market_context"), dict) else {}
    out: Dict[str, Any] = {}
    if market_ctx.get("global_sentiment") is not None:
        out["global_sentiment"] = market_ctx.get("global_sentiment")
    if market_ctx.get("market_breadth") is not None:
        out["market_breadth"] = market_ctx.get("market_breadth")
    if market_ctx.get("index_trend") is not None:
        out["index_trend"] = market_ctx.get("index_trend")
    if market_ctx.get("realized_volatility") is not None:
        out["realized_volatility"] = market_ctx.get("realized_volatility")
    if not out:
        global_sentiment = state.get("global_sentiment")
        if isinstance(global_sentiment, dict) and global_sentiment.get("score") is not None:
            out["global_sentiment"] = global_sentiment.get("score")
    return out


def feature_row_for_symbol(state: Dict[str, Any], symbol: str) -> tuple[Dict[str, Any], str]:
    sym = normalize_symbol(symbol)
    if not sym:
        return {}, "none"

    feature_engine = state.get("feature_engine") if isinstance(state.get("feature_engine"), dict) else {}
    by_symbol = feature_engine.get("by_symbol") if isinstance(feature_engine.get("by_symbol"), dict) else {}
    direct = by_symbol.get(sym)
    if isinstance(direct, dict) and direct:
        return dict(direct), "feature_engine.by_symbol"

    ohlcv_by_symbol = state.get("ohlcv_by_symbol") if isinstance(state.get("ohlcv_by_symbol"), dict) else {}
    rows = ohlcv_by_symbol.get(sym)
    if isinstance(rows, list) and rows:
        try:
            return build_feature_row(rows, **feature_context_from_state(state)), "ohlcv_by_symbol"
        except Exception:
            return {}, "ohlcv_build_failed"

    return {}, "none"


def prior_bar_low_for_symbol(state: Dict[str, Any], symbol: str) -> float | None:
    sym = normalize_symbol(symbol)
    if not sym:
        return None
    ohlcv_by_symbol = state.get("ohlcv_by_symbol") if isinstance(state.get("ohlcv_by_symbol"), dict) else {}
    rows = ohlcv_by_symbol.get(sym)
    if not isinstance(rows, list) or len(rows) < 2:
        return None
    prior = rows[-2] if isinstance(rows[-2], dict) else {}
    low = to_float(prior.get("low"))
    if low > 0.0:
        return float(low)
    return None


def monitor_selected_snapshot_for_symbol(
    state: Dict[str, Any],
    symbol: str,
    selected: Dict[str, Any] | None,
    *,
    position: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    sym = normalize_symbol(symbol)
    selected_symbol = normalize_symbol((selected or {}).get("symbol")) if isinstance(selected, dict) else ""
    selected_matches = bool(selected_symbol and selected_symbol == sym)
    base = dict(selected or {}) if selected_matches else {}
    base["symbol"] = sym

    quotes, _meta = extract_market_quotes(state)
    quote = quotes.get(sym) if isinstance(quotes.get(sym), dict) else {}

    price, price_source = resolve_price_with_source(state, sym, selected, position=position)
    if price is not None and to_float(price) > 0.0:
        base["price"] = float(price)

    features = base.get("features") if isinstance(base.get("features"), dict) else {}
    feature_source = "selected.features" if features else "none"
    if not features:
        feature_row, feature_source = feature_row_for_symbol(state, sym)
        if feature_row:
            features = feature_alias_map(feature_row, quote=quote)
    elif quote:
        enriched = dict(features)
        quote_alias = feature_alias_map({}, quote=quote)
        for key, value in quote_alias.items():
            if value in (None, ""):
                continue
            if key in {"skill_quote_price", "intraday_change_pct", "quote_volume", "quote_trading_value"}:
                enriched[key] = value
            elif enriched.get(key) in (None, ""):
                enriched[key] = value
        features = enriched

    if features:
        base["features"] = dict(features)
    base["_monitor_price_source"] = str(price_source)
    base["_monitor_quote_observed_epoch"] = quote_observed_epoch(quote)
    base["_monitor_feature_source"] = str(feature_source)
    prior_bar_low = prior_bar_low_for_symbol(state, sym)
    if prior_bar_low is not None and prior_bar_low > 0.0:
        base["_monitor_prior_bar_low"] = float(prior_bar_low)
    return base
