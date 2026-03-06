from __future__ import annotations

import json
import math
import os
import time
from typing import Any, Dict, List, Mapping, Optional

from libs.market.global_sentiment import compute_global_sentiment
from libs.news.news_pipeline import collect_news_items, score_news_sentiment
from libs.runtime.feature_engine import build_feature_map


_DEFAULT_SYMBOL_QUERY_MAP: Dict[str, str] = {
    "005930": "Samsung Electronics",
    "000660": "SK hynix",
    "035420": "NAVER",
    "051910": "LG Chem",
    "005380": "Hyundai Motor",
}

_DEFAULT_SYMBOL_YF_MAP: Dict[str, str] = {
    "005930": "005930.KS",
    "000660": "000660.KS",
    "035420": "035420.KS",
    "051910": "051910.KS",
    "005380": "005380.KS",
}


def _is_trueish(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _to_int(v: Any, default: int) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _to_num(v: Any) -> Optional[float]:
    try:
        x = float(v)
    except Exception:
        return None
    if not math.isfinite(x):
        return None
    return x


def _resolve_symbol(state: Dict[str, Any]) -> str:
    symbol = state.get("symbol") or state.get("selected_symbol")
    if not symbol:
        market = state.get("market_snapshot") if isinstance(state.get("market_snapshot"), dict) else {}
        symbol = market.get("symbol")
    return str(symbol or "").strip().upper()


def _parse_kv_map(raw: str) -> Dict[str, str]:
    s = str(raw or "").strip()
    if not s:
        return {}

    if s.startswith("{"):
        try:
            obj = json.loads(s)
        except Exception:
            return {}
        if not isinstance(obj, dict):
            return {}
        out: Dict[str, str] = {}
        for k, v in obj.items():
            ks = str(k or "").strip().upper()
            vs = str(v or "").strip()
            if ks and vs:
                out[ks] = vs
        return out

    out: Dict[str, str] = {}
    for token in s.replace(";", ",").split(","):
        part = str(token or "").strip()
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
        elif ":" in part:
            k, v = part.split(":", 1)
        else:
            continue
        ks = str(k or "").strip().upper()
        vs = str(v or "").strip()
        if ks and vs:
            out[ks] = vs
    return out


def _resolve_symbol_query_map() -> Dict[str, str]:
    env_raw = str(os.getenv("M10_SYMBOL_QUERY_MAP", "") or "").strip()
    if not env_raw:
        env_raw = str(os.getenv("SYMBOL_QUERY_MAP_JSON", "") or "").strip()
    env_map = _parse_kv_map(env_raw)

    allowlist = str(os.getenv("SYMBOL_ALLOWLIST", "") or "").strip()
    out: Dict[str, str] = {}
    for sym in allowlist.split(","):
        code = str(sym or "").strip().upper()
        if code in _DEFAULT_SYMBOL_QUERY_MAP:
            out[code] = _DEFAULT_SYMBOL_QUERY_MAP[code]

    out.update(env_map)
    return out


def _resolve_symbol_yf_map(policy: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}

    allowlist = str(os.getenv("SYMBOL_ALLOWLIST", "") or "").strip()
    for sym in allowlist.split(","):
        code = str(sym or "").strip().upper()
        if code in _DEFAULT_SYMBOL_YF_MAP:
            out[code] = _DEFAULT_SYMBOL_YF_MAP[code]

    env_raw = str(os.getenv("M10_SYMBOL_YF_MAP", "") or os.getenv("SYMBOL_YF_MAP_JSON", "") or "").strip()
    out.update(_parse_kv_map(env_raw))

    policy_map = policy.get("symbol_yf_map")
    if isinstance(policy_map, dict):
        for k, v in policy_map.items():
            ks = str(k or "").strip().upper()
            vs = str(v or "").strip()
            if ks and vs:
                out[ks] = vs
    return out


def _resolve_yf_ticker(symbol: str, policy: Dict[str, Any]) -> str:
    ymap = _resolve_symbol_yf_map(policy)
    if symbol in ymap:
        return str(ymap[symbol]).strip()
    if symbol.isdigit() and len(symbol) == 6:
        return f"{symbol}.KS"
    return symbol


def _policy_with_defaults(state: Dict[str, Any]) -> Dict[str, Any]:
    p = dict(state.get("policy") or {}) if isinstance(state.get("policy"), dict) else {}
    if "use_global_sentiment" not in p:
        p["use_global_sentiment"] = _is_trueish(os.getenv("M10_USE_GLOBAL_SENTIMENT", "true"))
    if "use_news_analysis" not in p:
        p["use_news_analysis"] = _is_trueish(os.getenv("M10_USE_NEWS_SENTIMENT", "true"))
    p.setdefault("news_provider", str(os.getenv("M10_NEWS_PROVIDER", "naver") or "naver"))
    p.setdefault("news_scorer", str(os.getenv("M10_NEWS_SCORER", "simple") or "simple"))
    if "symbol_query_map" not in p:
        sqm = _resolve_symbol_query_map()
        if sqm:
            p["symbol_query_map"] = sqm
    return p


def _resolve_refresh_sec(state: Dict[str, Any], policy: Dict[str, Any]) -> int:
    raw = policy.get("decision_context_refresh_sec")
    if raw is None:
        raw = os.getenv("M10_DECISION_CONTEXT_REFRESH_SEC", "300")
    return max(1, _to_int(raw, 300))


def _normalize_ohlcv_rows(rows: List[Mapping[str, Any]]) -> List[Dict[str, Any]]:
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
                "volume": float(volume),
            }
        )
    out.sort(key=lambda x: int(x.get("ts", 0)))
    return out


def _fetch_yfinance_seed(symbol: str, policy: Dict[str, Any]) -> List[Dict[str, Any]]:
    enable = policy.get("feature_seed_with_yf")
    if enable is None:
        enable = _is_trueish(os.getenv("M10_FEATURE_SEED_WITH_YF", "true"))
    if not bool(enable):
        return []

    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return []

    ticker = _resolve_yf_ticker(symbol, policy)
    period = str(policy.get("feature_seed_period") or os.getenv("M10_FEATURE_SEED_PERIOD", "3mo") or "3mo")
    interval = str(policy.get("feature_seed_interval") or os.getenv("M10_FEATURE_SEED_INTERVAL", "1d") or "1d")
    max_rows = max(30, _to_int(policy.get("feature_seed_max_rows") or os.getenv("M10_FEATURE_SEED_MAX_ROWS", "120"), 120))

    try:
        hist = yf.Ticker(ticker).history(period=period, interval=interval)
    except Exception:
        return []
    if hist is None or getattr(hist, "empty", True):
        return []

    rows: List[Dict[str, Any]] = []
    try:
        hist_tail = hist.tail(max_rows)
        for idx, row in hist_tail.iterrows():
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
        return []

    rows.sort(key=lambda x: int(x.get("ts", 0)))
    return rows


def _append_live_price_candle(rows: List[Dict[str, Any]], *, price: float, now_epoch: int) -> List[Dict[str, Any]]:
    if price <= 0.0:
        return rows

    if rows:
        last = dict(rows[-1] or {})
        last_ts = _to_int(last.get("ts"), 0)
        if last_ts == int(now_epoch):
            last_open = _to_float(last.get("open"), price)
            last_high = _to_float(last.get("high"), price)
            last_low = _to_float(last.get("low"), price)
            last_volume = _to_float(last.get("volume"), 1.0)
            rows[-1] = {
                "ts": int(now_epoch),
                "open": float(last_open),
                "high": float(max(last_high, price)),
                "low": float(min(last_low, price)),
                "close": float(price),
                "volume": float(max(last_volume, 1.0)),
            }
            return rows

    rows.append(
        {
            "ts": int(now_epoch),
            "open": float(price),
            "high": float(price),
            "low": float(price),
            "close": float(price),
            "volume": 1.0,
        }
    )
    return rows


def _merge_seed_if_needed(
    *,
    symbol: str,
    rows: List[Dict[str, Any]],
    policy: Dict[str, Any],
    min_rows: int,
) -> List[Dict[str, Any]]:
    if len(rows) >= min_rows:
        return rows
    seed = _fetch_yfinance_seed(symbol, policy)
    if not seed:
        return rows
    return seed


def _update_feature_context(state: Dict[str, Any], *, symbol: str, now_epoch: int, policy: Dict[str, Any]) -> Dict[str, Any]:
    ohlcv_root = state.get("ohlcv_by_symbol")
    if not isinstance(ohlcv_root, dict):
        ohlcv_root = {}

    rows_raw = ohlcv_root.get(symbol)
    rows_list = list(rows_raw) if isinstance(rows_raw, list) else []
    rows = _normalize_ohlcv_rows(rows_list)

    min_rows = max(20, _to_int(policy.get("feature_min_rows") or os.getenv("M10_FEATURE_MIN_ROWS", "40"), 40))
    rows = _merge_seed_if_needed(symbol=symbol, rows=rows, policy=policy, min_rows=min_rows)

    market = state.get("market_snapshot") if isinstance(state.get("market_snapshot"), dict) else {}
    current_price = _to_num(market.get("price")) or 0.0
    rows = _append_live_price_candle(rows, price=float(current_price), now_epoch=int(now_epoch))

    max_rows = max(50, _to_int(policy.get("feature_series_max_rows") or os.getenv("M10_FEATURE_SERIES_MAX_ROWS", "240"), 240))
    if len(rows) > max_rows:
        rows = rows[-max_rows:]

    if rows:
        ohlcv_root[symbol] = rows
        state["ohlcv_by_symbol"] = ohlcv_root

    feature_row: Dict[str, Any] = {}
    if rows:
        try:
            feature_row = dict(build_feature_map({symbol: rows}).get(symbol) or {})
        except Exception:
            feature_row = {}

    fe_root = state.get("feature_engine")
    if not isinstance(fe_root, dict):
        fe_root = {}
    by_symbol = fe_root.get("by_symbol")
    if not isinstance(by_symbol, dict):
        by_symbol = {}
    if feature_row:
        by_symbol[symbol] = feature_row
    fe_root["by_symbol"] = by_symbol
    fe_root["source"] = "state.ohlcv_by_symbol"
    state["feature_engine"] = fe_root
    return feature_row


def build_decision_context(state: Dict[str, Any]) -> Dict[str, Any]:
    """M10 context hydration: sentiment + feature context for decide_trade."""
    symbol = _resolve_symbol(state)
    if not symbol:
        return state

    policy = _policy_with_defaults(state)
    state["policy"] = policy

    now = int(time.time())
    refresh_sec = _resolve_refresh_sec(state, policy)
    feature_row = _update_feature_context(state, symbol=symbol, now_epoch=now, policy=policy)
    feature_regime = str(feature_row.get("regime") or "unknown")
    feature_signal = _to_float(feature_row.get("signal_score"), 0.0)

    cache_root = state.get("_decision_context_cache")
    if not isinstance(cache_root, dict):
        cache_root = {}
    cache_row = cache_root.get(symbol) if isinstance(cache_root.get(symbol), dict) else {}
    last_epoch = _to_int(cache_row.get("refreshed_epoch"), 0) if isinstance(cache_row, dict) else 0

    if last_epoch > 0 and (now - last_epoch) < refresh_sec:
        gs_cached = _to_float(cache_row.get("global_sentiment_score"), 0.0)
        ns_cached = _to_float(cache_row.get("news_sentiment_score"), 0.0)
        state["global_sentiment"] = {"score": float(gs_cached)}

        ns_map = dict(state.get("news_sentiment") or {}) if isinstance(state.get("news_sentiment"), dict) else {}
        ns_map[symbol] = float(ns_cached)
        state["news_sentiment"] = ns_map

        ni_map = dict(state.get("news_items") or {}) if isinstance(state.get("news_items"), dict) else {}
        if isinstance(cache_row.get("news_items"), list):
            ni_map[symbol] = list(cache_row.get("news_items") or [])
            state["news_items"] = ni_map

        state["decision_context_meta"] = {
            "symbol": symbol,
            "cached": True,
            "refresh_sec": int(refresh_sec),
            "last_refreshed_epoch": int(last_epoch),
            "global_sentiment_score": float(gs_cached),
            "news_sentiment_score": float(ns_cached),
            "feature_regime": feature_regime,
            "feature_signal_score": float(feature_signal),
        }
        state["_decision_context_cache"] = cache_root
        return state

    gs = 0.0
    if bool(policy.get("use_global_sentiment", True)):
        try:
            gs = float(compute_global_sentiment(state=state, policy=policy))
        except Exception:
            gs = 0.0
    state["global_sentiment"] = {"score": float(gs)}

    news_score = 0.0
    news_items: List[Any] = []
    if bool(policy.get("use_news_analysis", True)):
        try:
            items_by_symbol = collect_news_items([symbol], state=state, policy=policy)
            if isinstance(items_by_symbol, dict):
                news_items = list(items_by_symbol.get(symbol) or [])
            scores = score_news_sentiment(items_by_symbol, state=state, policy=policy)  # type: ignore[arg-type]
            if isinstance(scores, dict):
                news_score = _to_float(scores.get(symbol), 0.0)
        except Exception:
            news_score = 0.0
            news_items = []

    ns_map = dict(state.get("news_sentiment") or {}) if isinstance(state.get("news_sentiment"), dict) else {}
    ns_map[symbol] = float(news_score)
    state["news_sentiment"] = ns_map

    ni_map = dict(state.get("news_items") or {}) if isinstance(state.get("news_items"), dict) else {}
    ni_map[symbol] = list(news_items)
    state["news_items"] = ni_map

    cache_root[symbol] = {
        "refreshed_epoch": int(now),
        "global_sentiment_score": float(gs),
        "news_sentiment_score": float(news_score),
        "news_items": list(news_items),
        "feature_regime": feature_regime,
        "feature_signal_score": float(feature_signal),
    }
    state["_decision_context_cache"] = cache_root
    state["decision_context_meta"] = {
        "symbol": symbol,
        "cached": False,
        "refresh_sec": int(refresh_sec),
        "last_refreshed_epoch": int(now),
        "global_sentiment_score": float(gs),
        "news_sentiment_score": float(news_score),
        "feature_regime": feature_regime,
        "feature_signal_score": float(feature_signal),
    }
    return state
