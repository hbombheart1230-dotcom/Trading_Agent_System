from __future__ import annotations

import os
import time
from typing import Any, Dict

from libs.market.global_sentiment import compute_global_sentiment
from libs.news.news_pipeline import collect_news_items, score_news_sentiment


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


def _resolve_symbol(state: Dict[str, Any]) -> str:
    symbol = state.get("symbol") or state.get("selected_symbol")
    if not symbol:
        market = state.get("market_snapshot") if isinstance(state.get("market_snapshot"), dict) else {}
        symbol = market.get("symbol")
    return str(symbol or "").strip().upper()


def _policy_with_defaults(state: Dict[str, Any]) -> Dict[str, Any]:
    p = dict(state.get("policy") or {}) if isinstance(state.get("policy"), dict) else {}
    if "use_global_sentiment" not in p:
        p["use_global_sentiment"] = _is_trueish(os.getenv("M10_USE_GLOBAL_SENTIMENT", "true"))
    if "use_news_analysis" not in p:
        p["use_news_analysis"] = _is_trueish(os.getenv("M10_USE_NEWS_SENTIMENT", "true"))
    p.setdefault("news_provider", str(os.getenv("M10_NEWS_PROVIDER", "naver") or "naver"))
    p.setdefault("news_scorer", str(os.getenv("M10_NEWS_SCORER", "simple") or "simple"))
    return p


def _resolve_refresh_sec(state: Dict[str, Any], policy: Dict[str, Any]) -> int:
    raw = policy.get("decision_context_refresh_sec")
    if raw is None:
        raw = os.getenv("M10_DECISION_CONTEXT_REFRESH_SEC", "300")
    return max(1, _to_int(raw, 300))


def build_decision_context(state: Dict[str, Any]) -> Dict[str, Any]:
    """M10 context hydration: auto-populate sentiment context for decide_trade.

    Produces:
      - state['global_sentiment'] = {'score': float}
      - state['news_sentiment'] = {symbol: float, ...}
      - state['news_items'] = {symbol: [NewsItem, ...], ...}
      - state['decision_context_meta'] for observability
    """
    symbol = _resolve_symbol(state)
    if not symbol:
        return state

    policy = _policy_with_defaults(state)
    state["policy"] = policy

    now = int(time.time())
    refresh_sec = _resolve_refresh_sec(state, policy)

    cache_root = state.get("_decision_context_cache")
    if not isinstance(cache_root, dict):
        cache_root = {}
    cache_row = cache_root.get(symbol) if isinstance(cache_root.get(symbol), dict) else {}
    last_epoch = _to_int(cache_row.get("refreshed_epoch"), 0) if isinstance(cache_row, dict) else 0

    # In-memory per-symbol cache to avoid high-frequency external calls.
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
        }
        state["_decision_context_cache"] = cache_root
        return state

    # Compute global sentiment (safe fallback to 0.0 on error).
    gs = 0.0
    if bool(policy.get("use_global_sentiment", True)):
        try:
            gs = float(compute_global_sentiment(state=state, policy=policy))
        except Exception:
            gs = 0.0
    state["global_sentiment"] = {"score": float(gs)}

    # Compute per-symbol news sentiment (safe fallback to 0.0 on error).
    news_score = 0.0
    news_items = []
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
    }
    state["_decision_context_cache"] = cache_root
    state["decision_context_meta"] = {
        "symbol": symbol,
        "cached": False,
        "refresh_sec": int(refresh_sec),
        "last_refreshed_epoch": int(now),
        "global_sentiment_score": float(gs),
        "news_sentiment_score": float(news_score),
    }
    return state

