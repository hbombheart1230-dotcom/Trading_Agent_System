"""News collection + sentiment scoring pipeline.

This module provides stable functions used by strategist_node:
- collect_news_items(symbols, state, policy) -> dict[symbol, list[NewsItem]]
- score_news_sentiment(items_by_symbol, state, policy) -> dict[symbol, float]

Design goals:
- Test-first: state can inject mock outputs.
- Safe: DRY_RUN avoids network where possible (providers/scorers should gate too).
- Pluggable: provider + scorer are registries.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

try:
    from libs.news.providers.base import NewsItem
except Exception:  # pragma: no cover
    NewsItem = Any  # type: ignore

from libs.news.providers.registry import get_provider
from libs.news.scorers.registry import get_scorer


def collect_news_items(symbols: Sequence[str], *, state: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, List[NewsItem]]:
    """Collect news items for given symbols.

    Priority:
    1) state['mock_news_items'] if present (dict or list)
    2) provider selected by policy['news_provider'] (defaults to 'naver')

    Returns dict[symbol, list[NewsItem]] and guarantees all input symbols exist as keys.
    """
    syms = [str(s) for s in symbols]

    # 1) state injection
    if "mock_news_items" in state and state["mock_news_items"] is not None:
        injected = state["mock_news_items"]
        out: Dict[str, List[NewsItem]] = {s: [] for s in syms}
        if isinstance(injected, dict):
            for s in syms:
                v = injected.get(s)
                if isinstance(v, list):
                    out[s] = list(v)
                elif v is None:
                    out[s] = []
                else:
                    out[s] = [v]  # tolerate single item
            return out
        if isinstance(injected, list):
            # if list, caller is responsible for symbol field; we just return empty per symbol
            # to preserve previous behavior, store under special key '__all__'
            out["__all__"] = list(injected)
            return out

    # 2) provider
    provider_name = str(policy.get("news_provider") or "naver")
    provider = get_provider(provider_name)
    try:
        fetched = provider.fetch(symbols=syms, policy=policy)
    except TypeError:
        # tolerate old signature: fetch(symbol)
        fetched = {s: provider.fetch(symbol=s, policy=policy) for s in syms}  # type: ignore

    out = {s: [] for s in syms}
    if isinstance(fetched, dict):
        for s in syms:
            v = fetched.get(s)
            if isinstance(v, list):
                out[s] = list(v)
            elif v is None:
                out[s] = []
            else:
                out[s] = [v]
    return out


def score_news_sentiment(items_by_symbol: Mapping[str, List[NewsItem]], *, state: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, float]:
    """Score sentiment for each symbol.

    Priority:
    1) state['mock_news_sentiment'] if present (handled inside scorers too, but we short-circuit)
    2) scorer selected by policy['news_scorer'] (defaults to 'simple')

    Returns dict[symbol, float] and guarantees all keys from items_by_symbol exist.
    """
    symbols = [str(s) for s in items_by_symbol.keys()]

    if isinstance(state.get("mock_news_sentiment"), dict):
        out = {s: 0.0 for s in symbols}
        for k, v in state["mock_news_sentiment"].items():
            ks = str(k)
            if ks in out:
                try:
                    out[ks] = float(v)
                except Exception:
                    out[ks] = 0.0
        return out

    scorer_name = str(policy.get("news_scorer") or "simple")
    scorer = get_scorer(scorer_name)
    scores = scorer.score(items_by_symbol, state=state, policy=policy)

    # ensure defaults for all symbols
    out = {s: 0.0 for s in symbols}
    if isinstance(scores, dict):
        for s in symbols:
            if s in scores:
                try:
                    out[s] = float(scores[s])
                except Exception:
                    out[s] = 0.0
    return out


# Backwards-compatible alias used by some tests
def score_news_sentiment_simple(items_by_symbol: Mapping[str, List[NewsItem]], *, state: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, float]:
    scorer = get_scorer("simple")
    return scorer.score(items_by_symbol, state=state, policy=policy)
