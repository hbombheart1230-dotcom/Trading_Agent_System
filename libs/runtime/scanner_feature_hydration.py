from __future__ import annotations

import math
import os
import time
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from libs.runtime.feature_engine import build_feature_map


def _norm_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return int(default)


def _to_num(value: Any) -> float | None:
    try:
        out = float(value)
    except Exception:
        return None
    if not math.isfinite(out):
        return None
    return out


def _is_trueish(value: Any) -> bool:
    return str(value or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _normalize_ohlcv_rows(rows: Iterable[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        close = _to_num(row.get("close"))
        if close is None or close <= 0.0:
            continue
        open_p = _to_num(row.get("open"))
        high = _to_num(row.get("high"))
        low = _to_num(row.get("low"))
        volume = _to_num(row.get("volume"))
        ts = _to_int(row.get("ts"), 0)
        if open_p is None:
            open_p = close
        if high is None:
            high = max(open_p, close)
        if low is None:
            low = min(open_p, close)
        if volume is None or volume <= 0.0:
            volume = 1.0
        out.append(
            {
                "ts": int(ts),
                "open": float(open_p),
                "high": float(max(high, open_p, close)),
                "low": float(min(low, open_p, close)),
                "close": float(close),
                "volume": float(max(volume, 1.0)),
            }
        )
    out.sort(key=lambda row: int(row.get("ts", 0)))
    return out


def _append_live_price(rows: List[Dict[str, Any]], *, price: float, now_epoch: int) -> List[Dict[str, Any]]:
    if price <= 0.0:
        return rows
    copied = list(rows)
    if copied:
        last = dict(copied[-1] or {})
        if _to_int(last.get("ts"), 0) == int(now_epoch):
            open_p = _to_float(last.get("open"), price)
            high = _to_float(last.get("high"), price)
            low = _to_float(last.get("low"), price)
            volume = _to_float(last.get("volume"), 1.0)
            copied[-1] = {
                "ts": int(now_epoch),
                "open": float(open_p),
                "high": float(max(high, price)),
                "low": float(min(low, price)),
                "close": float(price),
                "volume": float(max(volume, 1.0)),
            }
            return copied
    copied.append(
        {
            "ts": int(now_epoch),
            "open": float(price),
            "high": float(price),
            "low": float(price),
            "close": float(price),
            "volume": 1.0,
        }
    )
    return copied


def _resolve_yf_ticker(symbol: str) -> str:
    if symbol.isdigit() and len(symbol) == 6:
        return f"{symbol}.KS"
    return symbol


def _fetch_seed_rows(symbol: str, *, policy: Dict[str, Any], state: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], str]:
    injected = state.get("scanner_feature_seed_rows")
    if isinstance(injected, dict):
        rows = injected.get(symbol)
        if isinstance(rows, list):
            return _normalize_ohlcv_rows(rows), "state.scanner_feature_seed_rows"

    enabled = policy.get("scanner_feature_seed_with_yf")
    if enabled is None:
        enabled = os.getenv("SCANNER_FEATURE_SEED_WITH_YF", "true")
    if not _is_trueish(enabled):
        return [], "disabled"

    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return [], "yfinance_unavailable"

    period = str(policy.get("scanner_feature_seed_period") or os.getenv("SCANNER_FEATURE_SEED_PERIOD", "3mo") or "3mo")
    interval = str(policy.get("scanner_feature_seed_interval") or os.getenv("SCANNER_FEATURE_SEED_INTERVAL", "1d") or "1d")
    max_rows = max(
        30,
        _to_int(policy.get("scanner_feature_seed_max_rows") or os.getenv("SCANNER_FEATURE_SEED_MAX_ROWS", "120"), 120),
    )
    ticker = _resolve_yf_ticker(symbol)
    try:
        hist = yf.Ticker(ticker).history(period=period, interval=interval)
    except Exception:
        return [], "yfinance_error"
    if hist is None or getattr(hist, "empty", True):
        return [], "yfinance_empty"

    rows: List[Dict[str, Any]] = []
    try:
        for idx, row in hist.tail(max_rows).iterrows():
            close = _to_num(row.get("Close"))
            if close is None or close <= 0.0:
                continue
            open_p = _to_num(row.get("Open")) or close
            high = _to_num(row.get("High")) or max(open_p, close)
            low = _to_num(row.get("Low")) or min(open_p, close)
            volume = _to_num(row.get("Volume")) or 1.0
            ts = 0
            try:
                ts = int(idx.timestamp())
            except Exception:
                ts = 0
            rows.append(
                {
                    "ts": int(ts),
                    "open": float(open_p),
                    "high": float(max(high, open_p, close)),
                    "low": float(min(low, open_p, close)),
                    "close": float(close),
                    "volume": float(max(volume, 1.0)),
                }
            )
    except Exception:
        return [], "yfinance_parse_error"
    rows.sort(key=lambda row: int(row.get("ts", 0)))
    return rows, "yfinance"


def hydrate_scanner_feature_map(
    *,
    state: Dict[str, Any],
    candidates: List[Any],
    skill_quotes: Dict[str, Dict[str, Any]],
    policy: Dict[str, Any],
) -> Tuple[Dict[str, Dict[str, Any]], str, List[str]]:
    feature_errors: List[str] = []
    candidate_symbols = []
    for item in candidates:
        if isinstance(item, dict):
            symbol = _norm_symbol(item.get("symbol"))
        else:
            symbol = _norm_symbol(item)
        if symbol and symbol not in candidate_symbols:
            candidate_symbols.append(symbol)
    if not candidate_symbols:
        return {}, "none", feature_errors

    direct = state.get("scanner_features")
    if isinstance(direct, dict):
        out = {}
        for symbol in candidate_symbols:
            value = direct.get(symbol)
            if isinstance(value, dict):
                out[symbol] = dict(value)
        if out:
            return out, "state.scanner_features", feature_errors

    fe_root = state.get("feature_engine") if isinstance(state.get("feature_engine"), dict) else {}
    fe_by_symbol = fe_root.get("by_symbol") if isinstance(fe_root.get("by_symbol"), dict) else {}
    out_existing: Dict[str, Dict[str, Any]] = {}
    missing_symbols: List[str] = []
    for symbol in candidate_symbols:
        value = fe_by_symbol.get(symbol)
        if isinstance(value, dict) and value:
            out_existing[symbol] = dict(value)
        else:
            missing_symbols.append(symbol)
    if not missing_symbols and out_existing:
        return out_existing, "state.feature_engine.by_symbol", feature_errors

    ohlcv_root = state.get("ohlcv_by_symbol") if isinstance(state.get("ohlcv_by_symbol"), dict) else {}
    ohlcv_root = dict(ohlcv_root)
    preexisting_ohlcv = {
        symbol: list(rows)
        for symbol, rows in ohlcv_root.items()
        if isinstance(rows, list) and rows
    }
    cache_root = state.get("_scanner_feature_cache") if isinstance(state.get("_scanner_feature_cache"), dict) else {}
    cache_root = dict(cache_root)
    now_epoch = int(time.time())
    min_rows = max(20, _to_int(policy.get("scanner_feature_min_rows") or os.getenv("SCANNER_FEATURE_MIN_ROWS", "40"), 40))
    max_rows = max(50, _to_int(policy.get("scanner_feature_series_max_rows") or os.getenv("SCANNER_FEATURE_SERIES_MAX_ROWS", "240"), 240))
    refresh_sec = max(60, _to_int(policy.get("scanner_feature_seed_refresh_sec") or os.getenv("SCANNER_FEATURE_SEED_REFRESH_SEC", "1800"), 1800))
    fetched_sources: List[str] = []

    for symbol in candidate_symbols:
        raw_rows = ohlcv_root.get(symbol)
        rows = _normalize_ohlcv_rows(raw_rows) if isinstance(raw_rows, list) else []
        cache_meta = cache_root.get(symbol) if isinstance(cache_root.get(symbol), dict) else {}
        last_seed_epoch = _to_int(cache_meta.get("seed_epoch"), 0)
        seed_stale = last_seed_epoch <= 0 or (now_epoch - last_seed_epoch) >= refresh_sec
        if len(rows) < min_rows and seed_stale:
            seed_rows, seed_source = _fetch_seed_rows(symbol, policy=policy, state=state)
            if seed_rows:
                rows = list(seed_rows)
                cache_root[symbol] = {"seed_epoch": int(now_epoch), "seed_source": seed_source}
                fetched_sources.append(seed_source)
            elif seed_source not in ("disabled",):
                feature_errors.append(f"seed:{symbol}:{seed_source}")

        quote = skill_quotes.get(symbol) if isinstance(skill_quotes.get(symbol), dict) else {}
        live_price = quote.get("price")
        if live_price is None:
            live_price = quote.get("cur")
        live_price_num = _to_num(live_price) or 0.0
        rows = _append_live_price(rows, price=float(live_price_num), now_epoch=now_epoch)
        if len(rows) > max_rows:
            rows = rows[-max_rows:]
        if rows:
            ohlcv_root[symbol] = rows

    state["ohlcv_by_symbol"] = ohlcv_root
    state["_scanner_feature_cache"] = cache_root

    candidate_ohlcv = {
        symbol: ohlcv_root.get(symbol)
        for symbol in candidate_symbols
        if isinstance(ohlcv_root.get(symbol), list) and ohlcv_root.get(symbol)
    }
    if not candidate_ohlcv:
        return out_existing, "none", feature_errors

    market_context = state.get("market_context") if isinstance(state.get("market_context"), dict) else {}
    context: Dict[str, Any] = {"global_sentiment": _to_float((state.get("global_sentiment_signal") or {}).get("score"), 0.0)}
    if market_context.get("market_breadth") is not None:
        context["market_breadth"] = market_context.get("market_breadth")
    if market_context.get("index_trend") is not None:
        context["index_trend"] = market_context.get("index_trend")
    if market_context.get("realized_vol") is not None:
        context["realized_vol"] = market_context.get("realized_vol")

    try:
        built = build_feature_map(
            candidate_ohlcv,
            trend_gap_threshold=float(policy.get("feature_trend_gap_threshold") or 0.01),
            high_vol_threshold=float(policy.get("feature_high_vol_threshold") or 0.03),
            context=context,
        )
    except Exception as exc:
        feature_errors.append(f"feature_engine:error:{type(exc).__name__}")
        return out_existing, "none", feature_errors

    merged = dict(fe_root)
    merged_by_symbol = dict(fe_by_symbol)
    normalized_built = {_norm_symbol(symbol): dict(value) for symbol, value in built.items() if _norm_symbol(symbol) and isinstance(value, dict)}
    merged_by_symbol.update(normalized_built)
    merged["by_symbol"] = merged_by_symbol
    merged["source"] = "scanner_candidate_hydration"
    state["feature_engine"] = merged

    out: Dict[str, Dict[str, Any]] = {}
    for symbol in candidate_symbols:
        value = merged_by_symbol.get(symbol)
        if isinstance(value, dict):
            out[symbol] = dict(value)

    all_candidates_preseeded = all(symbol in preexisting_ohlcv for symbol in candidate_symbols)
    if fetched_sources:
        source = "scanner_candidate_hydration:" + "+".join(sorted(set(fetched_sources)))
    elif all_candidates_preseeded:
        source = "state.ohlcv_by_symbol"
    else:
        source = "scanner_candidate_hydration"
    return out, source, feature_errors
