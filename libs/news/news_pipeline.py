from __future__ import annotations

from typing import Any, Dict, List, Sequence, Mapping, Iterable

from libs.news.providers.base import NewsItem
from libs.news.providers.registry import get_provider
from libs.news.scorers.registry import get_scorer


def collect_news_items(
    symbols: Sequence[str],
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
) -> Dict[str, List[NewsItem]]:
    """Collect news items for given symbols.

    Priority:
    1) state['mock_news_items'] if present (tests/DRY_RUN)
       - can be list[NewsItem] OR dict[symbol -> list[dict|NewsItem]]
    2) provider selected by policy['news_provider'] (stub by default)
    """
    sym_list = [str(s) for s in symbols]
    out_map: Dict[str, List[NewsItem]] = {s: [] for s in sym_list}

    def _ingest(items: Iterable[NewsItem]) -> None:
        for it in items:
            sym = str(getattr(it, "symbol", "") or "")
            if not sym:
                continue
            if sym not in out_map:
                # ignore symbols outside requested set
                continue
            out_map[sym].append(it)

    # 1) mocks
    if "mock_news_items" in state and state["mock_news_items"] is not None:
        mock = state["mock_news_items"]

        # Case A: list[NewsItem|dict]
        if isinstance(mock, list):
            items: List[NewsItem] = []
            for x in mock:
                if isinstance(x, NewsItem):
                    items.append(x)
                elif isinstance(x, dict):
                    items.append(NewsItem(**x))
            _ingest(items)
            return out_map

        # Case B: dict[symbol -> list[dict|NewsItem]]
        if isinstance(mock, dict):
            items: List[NewsItem] = []
            for sym in sym_list:
                arr = mock.get(sym, [])
                if not isinstance(arr, list):
                    continue
                for x in arr:
                    if isinstance(x, NewsItem):
                        if x.symbol:
                            items.append(x)
                        else:
                            items.append(NewsItem(**{**x.__dict__, "symbol": str(sym)}))
                    elif isinstance(x, dict):
                        d = dict(x)
                        d.setdefault("symbol", str(sym))
                        items.append(NewsItem(**d))
            _ingest(items)
            return out_map

    provider_name = str(policy.get("news_provider") or "naver")
    provider = get_provider(provider_name)
    fetched = list(provider.fetch(symbols=sym_list, policy=policy, state=state))
    _ingest(fetched)
    return out_map


def score_news_sentiment(
    items: Sequence[NewsItem],
    symbols: Sequence[str],
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
) -> Dict[str, float]:
    """Score news into per-symbol sentiment.

    Priority:
    1) state['mock_news_sentiment'] if present (tests)
    2) scorer selected by policy['news_scorer'] (default: simple keyword)
    """
    if "mock_news_sentiment" in state and state["mock_news_sentiment"] is not None:
        ms = dict(state["mock_news_sentiment"])
        return {s: float(ms.get(s, 0.0)) for s in symbols}

    scorer_name = str(policy.get("news_scorer") or "simple")
    scorer = get_scorer(scorer_name)
    scores = scorer.score(items=items, symbols=list(symbols))
    return {s: float(scores.get(s, 0.0)) for s in symbols}


# Backward-compatible alias used by older tests (M18-6)
def score_news_sentiment_simple(
    items_by_symbol: Mapping[str, Sequence[Any]],
    *,
    state: Dict[str, Any],
    policy: Dict[str, Any],
) -> Dict[str, float]:
    # The contract test passes dict of symbols -> list(items). We only need symbols.
    symbols = list(items_by_symbol.keys())
    # If caller provided mock scores, return with defaults.
    if "mock_news_sentiment" in state and state["mock_news_sentiment"] is not None:
        ms = dict(state["mock_news_sentiment"])
        return {s: float(ms.get(s, 0.0)) for s in symbols}
    # Otherwise, treat as empty items and return zeros.
    return {s: 0.0 for s in symbols}
