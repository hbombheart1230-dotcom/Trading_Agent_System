from typing import Any, Dict, List, Mapping, Sequence
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from libs.news.models import NewsItem
from libs.news.providers.registry import get_provider
from libs.news.scorers.registry import get_scorer
from libs.data_quality.signal_contract import (
    SIGNAL_STATUS_FALLBACK,
    SIGNAL_STATUS_OK,
    SIGNAL_STATUS_UNAVAILABLE,
    make_signal,
    normalize_signal_score,
)

import os
import time
import math


def _is_trueish(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v or "").strip().lower()
    return s in ("1", "true", "yes", "y", "on")


def _parse_symbol_yf_map_env() -> Dict[str, str]:
    raw = str(os.getenv("M10_SYMBOL_YF_MAP", "") or "").strip()
    out: Dict[str, str] = {}
    if not raw:
        return out
    for token in raw.split(","):
        part = str(token or "").strip()
        if not part or "=" not in part:
            continue
        sym, ticker = part.split("=", 1)
        sym_s = str(sym or "").strip()
        tick_s = str(ticker or "").strip()
        if sym_s and tick_s:
            out[sym_s] = tick_s
    return out


def _resolve_yf_ticker(symbol: str, policy: Dict[str, Any]) -> str:
    sym = str(symbol or "").strip()
    mapping = dict(policy.get("symbol_yf_map") or {})
    if not mapping:
        mapping = _parse_symbol_yf_map_env()
    if sym in mapping:
        return str(mapping[sym])
    if sym.isdigit() and len(sym) == 6:
        return f"{sym}.KS"
    return sym


def _fetch_yfinance_news_items(symbol: str, policy: Dict[str, Any]) -> List[NewsItem]:
    try:
        import yfinance as yf  # type: ignore
    except Exception:
        return []

    ticker = _resolve_yf_ticker(symbol, policy)
    try:
        raw_news = yf.Ticker(ticker).news or []
    except Exception:
        return []

    out: List[NewsItem] = []
    max_items = int(policy.get("news_max_items_per_symbol") or 5)
    for row in list(raw_news)[:max_items]:
        if not isinstance(row, dict):
            continue
        content = row.get("content") if isinstance(row.get("content"), dict) else {}
        title = _as_str(row.get("title") or content.get("title")).strip()
        if not title:
            continue
        canonical = content.get("canonicalUrl") if isinstance(content.get("canonicalUrl"), dict) else {}
        click = content.get("clickThroughUrl") if isinstance(content.get("clickThroughUrl"), dict) else {}
        provider = content.get("provider") if isinstance(content.get("provider"), dict) else {}
        url = _as_str(
            row.get("link")
            or canonical.get("url")
            or click.get("url")
        )
        published_at = _as_str(row.get("providerPublishTime") or content.get("pubDate") or content.get("displayTime"))
        summary = _as_str(row.get("summary") or content.get("summary") or content.get("description"))
        source = _as_str(row.get("publisher") or provider.get("displayName") or "yfinance")
        out.append(
            NewsItem(
                title=title,
                url=url,
                source=source,
                published_at=published_at,
                symbol=str(symbol),
                summary=summary,
                raw=row,
            )
        )
    return out


# -------------------------------------------------
# NEWS COLLECTION
# -------------------------------------------------


def _as_str(v: Any) -> str:
    if v is None:
        return ""
    return str(v)


def _to_news_item(obj: Any, *, symbol_hint: str | None = None) -> NewsItem | None:
    """Normalize provider/test payloads into libs.news.models.NewsItem."""
    if isinstance(obj, NewsItem):
        if obj.symbol:
            return obj
        if symbol_hint:
            return NewsItem(
                title=obj.title,
                url=obj.url,
                source=obj.source,
                published_at=obj.published_at,
                symbol=str(symbol_hint),
                summary=obj.summary,
                raw=obj.raw,
            )
        return None

    if isinstance(obj, dict):
        title = _as_str(obj.get("title")).strip()
        symbol = _as_str(obj.get("symbol") or symbol_hint).strip()
        if not title or not symbol:
            return None
        return NewsItem(
            title=title,
            url=_as_str(obj.get("url")),
            source=_as_str(obj.get("source")),
            published_at=_as_str(obj.get("published_at")),
            symbol=symbol,
            summary=_as_str(obj.get("summary")),
            raw=obj if isinstance(obj, dict) else None,
        )

    title = _as_str(getattr(obj, "title", "")).strip()
    symbol = _as_str(getattr(obj, "symbol", None) or symbol_hint).strip()
    if not title or not symbol:
        return None
    return NewsItem(
        title=title,
        url=_as_str(getattr(obj, "url", "")),
        source=_as_str(getattr(obj, "source", "")),
        published_at=_as_str(getattr(obj, "published_at", "")),
        symbol=symbol,
        summary=_as_str(getattr(obj, "summary", "")),
        raw=None,
    )

def collect_news_items(
    symbols: Sequence[str],
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
):
    """
    Return: Dict[symbol, List[NewsItem]]
    """

    # 1) test / dry-run mock
    if state.get("mock_news_items") is not None:
        mock = state["mock_news_items"] if isinstance(state.get("mock_news_items"), dict) else {}
        out: Dict[str, List[NewsItem]] = {}
        for s in symbols:
            sym = str(s)
            norm: List[NewsItem] = []
            for row in list(mock.get(sym, []) or []):
                item = _to_news_item(row, symbol_hint=sym)
                if item is not None:
                    norm.append(item)
            out[sym] = norm
        return out

    provider_name = str(policy.get("news_provider") or "naver")
    provider = get_provider(provider_name)
    try:
        fetched = provider.fetch(symbols=list(symbols), state=state, policy=policy)
    except TypeError:
        try:
            fetched = provider.fetch(symbols=list(symbols), policy=policy)
        except TypeError:
            fetched = provider.fetch(list(symbols), policy)

    items_by_symbol: Dict[str, List[NewsItem]] = defaultdict(list)
    if isinstance(fetched, Mapping):
        for sym, rows in fetched.items():
            sym_s = str(sym)
            for row in list(rows or []):
                item = _to_news_item(row, symbol_hint=sym_s)
                if item is not None:
                    items_by_symbol[sym_s].append(item)
    else:
        for row in list(fetched or []):
            item = _to_news_item(row)
            if item is not None:
                items_by_symbol[str(item.symbol)].append(item)

    # ensure all symbols exist
    out = {str(s): list(items_by_symbol.get(str(s), [])) for s in symbols}

    # Optional yfinance fallback when provider returns no news.
    yf_fallback_enabled = policy.get("news_yf_fallback_enabled")
    if yf_fallback_enabled is None:
        yf_fallback_enabled = os.getenv("M10_NEWS_YF_FALLBACK", "true")
    if _is_trueish(yf_fallback_enabled):
        for s in symbols:
            sym = str(s)
            if out.get(sym):
                continue
            yf_items = _fetch_yfinance_news_items(sym, policy)
            if yf_items:
                out[sym] = yf_items
    return out


# -------------------------------------------------
# SIMPLE SCORER DIRECT ACCESS (test용)
# -------------------------------------------------

def score_news_sentiment_simple(
    items_by_symbol: Mapping[str, List[NewsItem]],
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
) -> Dict[str, float]:
    """
    테스트 계약:
    - mock_news_sentiment 있으면 그 값 우선
    - 없으면 0.0
    """

    mock_scores = state.get("mock_news_sentiment") or {}

    scores = {}
    for symbol in items_by_symbol.keys():
        if symbol in mock_scores:
            scores[symbol] = float(mock_scores[symbol])
        else:
            scores[symbol] = 0.0

    return scores

# -------------------------------------------------
# MAIN SENTIMENT ROUTER
# -------------------------------------------------

def _normalize_items_for_scoring(
    items_by_symbol=None,
    *,
    items: List[NewsItem] | None = None,
    symbols: Sequence[str] | None = None,
) -> tuple[Dict[str, List[NewsItem]], List[str]]:
    norm: Dict[str, List[NewsItem]] = {}

    # case (2): items + symbols
    if items_by_symbol is None and items is not None:
        tmp: Dict[str, List[NewsItem]] = {}
        for it in items:
            norm_item = _to_news_item(it)
            if norm_item is None:
                continue
            tmp.setdefault(str(norm_item.symbol), []).append(norm_item)
        if symbols is not None:
            for s in symbols:
                tmp.setdefault(str(s), [])
        norm = tmp

    # case (1): items_by_symbol passed (may contain dicts)
    elif isinstance(items_by_symbol, dict):
        for sym, arr in items_by_symbol.items():
            sym_s = str(sym)
            out_list: List[NewsItem] = []
            for x in (arr or []):
                norm_item = _to_news_item(x, symbol_hint=sym_s)
                if norm_item is not None:
                    out_list.append(norm_item)
            norm[sym_s] = out_list

    # if still no symbols, derive from norm keys
    all_symbols = list(norm.keys())
    if symbols is not None:
        all_symbols = [str(s) for s in symbols]
        for s in all_symbols:
            norm.setdefault(str(s), [])
    return norm, all_symbols


def _normalize_headline_key(text: Any) -> str:
    raw = _as_str(text).strip().lower()
    if not raw:
        return ""
    compact = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in raw)
    return " ".join(compact.split())


def _parse_news_timestamp(value: Any) -> int | None:
    text = _as_str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        pass
    try:
        dt = parsedate_to_datetime(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def _resolve_news_decay_policy(policy: Dict[str, Any]) -> Dict[str, float]:
    half_life_sec = float(policy.get("news_sentiment_freshness_half_life_sec") or os.getenv("NEWS_SENTIMENT_FRESHNESS_HALF_LIFE_SEC", "3600"))
    min_freshness_weight = float(policy.get("news_sentiment_min_freshness_weight") or os.getenv("NEWS_SENTIMENT_MIN_FRESHNESS_WEIGHT", "0.35"))
    min_duplicate_weight = float(policy.get("news_sentiment_min_duplicate_weight") or os.getenv("NEWS_SENTIMENT_MIN_DUPLICATE_WEIGHT", "0.40"))
    return {
        "half_life_sec": max(300.0, half_life_sec),
        "min_freshness_weight": max(0.10, min(1.0, min_freshness_weight)),
        "min_duplicate_weight": max(0.10, min(1.0, min_duplicate_weight)),
    }


def _news_symbol_decay_meta(rows: List[NewsItem], *, now_epoch: int, policy: Dict[str, Any]) -> Dict[str, Any]:
    cfg = _resolve_news_decay_policy(policy)
    if not rows:
        return {
            "headline_count": 0,
            "distinct_headline_count": 0,
            "freshness_weight": 1.0,
            "duplicate_weight": 1.0,
        }

    headline_keys = [_normalize_headline_key(getattr(row, "title", "")) for row in rows]
    headline_keys = [k for k in headline_keys if k]
    distinct_count = len(set(headline_keys)) if headline_keys else 0
    duplicate_weight = 1.0
    if headline_keys:
        duplicate_weight = max(
            cfg["min_duplicate_weight"],
            float(distinct_count) / float(max(1, len(headline_keys))),
        )

    freshness_weights: List[float] = []
    for row in rows:
        ts = _parse_news_timestamp(getattr(row, "published_at", ""))
        if ts is None:
            freshness_weights.append(1.0)
            continue
        age_sec = max(0, int(now_epoch - ts))
        weight = math.pow(0.5, float(age_sec) / float(cfg["half_life_sec"]))
        freshness_weights.append(weight)
    freshness_weight = 1.0
    if freshness_weights:
        freshness_weight = max(
            cfg["min_freshness_weight"],
            sum(freshness_weights) / float(len(freshness_weights)),
        )

    return {
        "headline_count": int(len(rows)),
        "distinct_headline_count": int(distinct_count or len(rows)),
        "freshness_weight": float(freshness_weight),
        "duplicate_weight": float(duplicate_weight),
    }


def score_news_sentiment(
    items_by_symbol=None,
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
    items: List[NewsItem] | None = None,
    symbols: Sequence[str] | None = None,
    preserve_unavailable_nan: bool = False,
) -> Dict[str, float]:
    """Legacy float-only score map.

    Prefer `score_news_sentiment_signal` for decision pipelines that require
    clear fallback/unavailable status semantics.
    """
    signals = score_news_sentiment_signal(
        items_by_symbol,
        state=state,
        policy=policy,
        items=items,
        symbols=symbols,
    )
    out: Dict[str, float] = {}
    for s, v in signals.items():
        status = str(v.get("status") or "").strip().lower()
        if bool(preserve_unavailable_nan) and status == SIGNAL_STATUS_UNAVAILABLE:
            out[s] = float("nan")
            continue
        out[s] = normalize_signal_score(v.get("score"), default=0.0)
    return out


def score_news_sentiment_signal(
    items_by_symbol=None,
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
    items: List[NewsItem] | None = None,
    symbols: Sequence[str] | None = None,
) -> Dict[str, Dict[str, Any]]:
    """Return per-symbol sentiment with data-quality state contract."""
    norm, all_symbols = _normalize_items_for_scoring(
        items_by_symbol,
        items=items,
        symbols=symbols,
    )
    now = int(time.time())

    mock = state.get("mock_news_sentiment")
    if isinstance(mock, dict):
        out: Dict[str, Dict[str, Any]] = {}
        for s in all_symbols:
            if s in mock:
                out[s] = make_signal(
                    score=mock.get(s, 0.0),
                    status=SIGNAL_STATUS_OK,
                    source="mock_news_sentiment",
                    reason="",
                    ts=now,
                )
            else:
                out[s] = make_signal(
                    score=0.0,
                    status=SIGNAL_STATUS_FALLBACK,
                    source="mock_news_sentiment",
                    reason="mock_missing_symbol_default",
                    ts=now,
                )
        return out

    scorer_name = str(policy.get("news_scorer") or "simple")
    if os.getenv("DRY_RUN", "0") == "1" and scorer_name.lower() in ("openrouter",):
        return {
            s: make_signal(
                score=0.0,
                status=SIGNAL_STATUS_FALLBACK,
                source="dry_run_policy",
                reason="dry_run_openrouter_neutral",
                ts=now,
            )
            for s in all_symbols
        }

    scorer = get_scorer(scorer_name)
    try:
        raw_scores = scorer.score(norm, state=state, policy=policy)
    except TypeError:
        raw_scores = scorer.score(norm)
    except Exception as exc:
        return {
            s: make_signal(
                score=0.0,
                status=SIGNAL_STATUS_UNAVAILABLE,
                source=f"scorer:{scorer_name}",
                reason=f"scorer_error:{type(exc).__name__}",
                ts=now,
            )
            for s in all_symbols
        }

    out: Dict[str, Dict[str, Any]] = {}
    raw_map = raw_scores if isinstance(raw_scores, dict) else {}
    for s in all_symbols:
        if s not in raw_map:
            out[s] = make_signal(
                score=0.0,
                status=SIGNAL_STATUS_FALLBACK,
                source=f"scorer:{scorer_name}",
                reason="missing_symbol_score",
                ts=now,
            )
            continue
        try:
            raw_score = float(raw_map.get(s))
            decay_meta = _news_symbol_decay_meta(norm.get(s, []), now_epoch=now, policy=policy)
            adjusted_score = raw_score * float(decay_meta.get("freshness_weight") or 1.0) * float(decay_meta.get("duplicate_weight") or 1.0)
            signal = make_signal(
                score=adjusted_score,
                status=SIGNAL_STATUS_OK,
                source=f"scorer:{scorer_name}",
                reason="",
                ts=now,
            )
            signal["raw_score"] = normalize_signal_score(raw_score, default=0.0)
            signal["freshness_weight"] = float(decay_meta.get("freshness_weight") or 1.0)
            signal["duplicate_weight"] = float(decay_meta.get("duplicate_weight") or 1.0)
            signal["headline_count"] = int(decay_meta.get("headline_count") or 0)
            signal["distinct_headline_count"] = int(decay_meta.get("distinct_headline_count") or 0)
            if signal["freshness_weight"] < 0.999 or signal["duplicate_weight"] < 0.999:
                reasons = []
                if signal["freshness_weight"] < 0.999:
                    reasons.append("freshness_decay")
                if signal["duplicate_weight"] < 0.999:
                    reasons.append("duplicate_headline_decay")
                signal["reason"] = ",".join(reasons)
            out[s] = signal
        except Exception:
            out[s] = make_signal(
                score=0.0,
                status=SIGNAL_STATUS_FALLBACK,
                source=f"scorer:{scorer_name}",
                reason="invalid_symbol_score",
                ts=now,
            )
    return out
