from typing import Any, Dict, List, Mapping, Sequence
from collections import defaultdict

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
    return {str(s): list(items_by_symbol.get(str(s), [])) for s in symbols}


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


def score_news_sentiment(
    items_by_symbol=None,
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
    items: List[NewsItem] | None = None,
    symbols: Sequence[str] | None = None,
) -> Dict[str, float]:
    signals = score_news_sentiment_signal(
        items_by_symbol,
        state=state,
        policy=policy,
        items=items,
        symbols=symbols,
    )
    return {s: normalize_signal_score(v.get("score"), default=0.0) for s, v in signals.items()}


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
            out[s] = make_signal(
                score=float(raw_map.get(s)),
                status=SIGNAL_STATUS_OK,
                source=f"scorer:{scorer_name}",
                reason="",
                ts=now,
            )
        except Exception:
            out[s] = make_signal(
                score=0.0,
                status=SIGNAL_STATUS_FALLBACK,
                source=f"scorer:{scorer_name}",
                reason="invalid_symbol_score",
                ts=now,
            )
    return out
