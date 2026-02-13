from typing import Any, Dict, List, Mapping, Sequence
from collections import defaultdict

from libs.news.models import NewsItem
from libs.news.providers.registry import get_provider
from libs.news.scorers.registry import get_scorer

import os

# -------------------------------------------------
# NEWS COLLECTION
# -------------------------------------------------

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
        mock = state["mock_news_items"]
        out = {}
        for s in symbols:
            out[s] = mock.get(s, [])
        return out

    provider_name = str(policy.get("news_provider") or "naver")
    provider = get_provider(provider_name)

    items = provider.fetch(symbols=list(symbols), policy=policy)

    items_by_symbol = defaultdict(list)
    for item in items:
        items_by_symbol[item.symbol].append(item)

    # ensure all symbols exist
    return {s: items_by_symbol.get(s, []) for s in symbols}


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

def score_news_sentiment(
    items_by_symbol=None,
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
    items: List[NewsItem] | None = None,
    symbols: Sequence[str] | None = None,
) -> Dict[str, float]:
    """
    Backward/forward compatible scorer entrypoint.

    Supported calls:
      1) score_news_sentiment(items_by_symbol, state=..., policy=...)
         - items_by_symbol: {symbol: [NewsItem|dict, ...], ...}

      2) score_news_sentiment(state=..., policy=..., items=[NewsItem...], symbols=[...])
         - used by some earlier tests/paths

    Priority:
      A) state['mock_news_sentiment'] -> always wins (fills missing with 0.0)
      B) DRY_RUN + openrouter -> returns 0.0 for all symbols (unless mock provided)
      C) otherwise dispatch scorer via registry (simple/llm/openrouter)
    """
    # ---------- normalize items_by_symbol ----------
    norm: Dict[str, List[NewsItem]] = {}

    # case (2): items + symbols
    if items_by_symbol is None and items is not None:
        # group by symbol field (if missing, ignore)
        tmp: Dict[str, List[NewsItem]] = {}
        for it in items:
            sym = getattr(it, "symbol", None)
            if not sym:
                continue
            tmp.setdefault(str(sym), []).append(it)
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
                if isinstance(x, NewsItem):
                    out_list.append(x)
                elif isinstance(x, dict):
                    # tolerate minimal dicts from tests
                    out_list.append(
                        NewsItem(
                            title=str(x.get("title", "")),
                            url=str(x.get("url", "")),
                            source=str(x.get("source", "")),
                            published_at=str(x.get("published_at", "")),
                            symbol=sym_s,
                            summary=str(x.get("summary", "")),
                        )
                    )
            norm[sym_s] = out_list
    else:
        norm = {}

    # if still no symbols, derive from norm keys
    all_symbols = list(norm.keys())
    if symbols is not None:
        all_symbols = [str(s) for s in symbols]
        for s in all_symbols:
            norm.setdefault(str(s), [])

    # ---------- mock wins ----------
    mock = state.get("mock_news_sentiment")
    if isinstance(mock, dict):
        out: Dict[str, float] = {}
        for s in all_symbols:
            v = mock.get(s, 0.0)
            try:
                out[s] = float(v)
            except Exception:
                out[s] = 0.0
        return out

    # ---------- DRY_RUN behavior for openrouter ----------
    scorer_name = str(policy.get("news_scorer") or "simple")
    if os.getenv("DRY_RUN", "0") == "1" and scorer_name.lower() in ("openrouter",):
        return {s: 0.0 for s in all_symbols}

    # ---------- dispatch scorer ----------
    scorer = get_scorer(scorer_name)
    # tolerate scorers that don't accept state/policy kwargs
    try:
        return scorer.score(norm, state=state, policy=policy)
    except TypeError:
        return scorer.score(norm)
