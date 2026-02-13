from __future__ import annotations

from typing import Dict, Any, Sequence, List, Mapping

from .providers.base import NewsItem, NewsProvider
from .providers.registry import NewsProviderRegistry


def normalize_symbols(symbols: Sequence[str]) -> List[str]:
    out: List[str] = []
    seen = set()
    for s in symbols:
        s = str(s).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def collect_news_items(
    symbols: Sequence[str],
    *,
    state: Dict[str, Any] | None = None,
    policy: Dict[str, Any] | None = None,
    provider: NewsProvider | None = None,
    registry: NewsProviderRegistry | None = None,
) -> Dict[str, List[NewsItem]]:
    """Collects news items per symbol.

    Order of resolution:
      1) If state contains mock_news_items (dict symbol -> list[dict|NewsItem]), use it.
      2) If provider explicitly provided, use it.
      3) If registry provided and policy.news_provider set, resolve and use it.
      4) Else return empty lists for all symbols.

    This keeps tests deterministic and avoids accidental network usage in early milestones.
    """
    state = state or {}
    policy = policy or {}
    symbols_n = normalize_symbols(symbols)

    mock = state.get("mock_news_items")
    if isinstance(mock, dict):
        out: Dict[str, List[NewsItem]] = {}
        for sym in symbols_n:
            raw_list = mock.get(sym, [])
            items: List[NewsItem] = []
            for r in raw_list:
                if isinstance(r, NewsItem):
                    items.append(r)
                elif isinstance(r, dict):
                    items.append(NewsItem(
                        title=str(r.get("title") or ""),
                        published_at=r.get("published_at"),
                        source=r.get("source"),
                        url=r.get("url"),
                    ))
            out[sym] = items
        return out

    use_provider = provider
    if use_provider is None and registry is not None:
        use_provider = registry.resolve(policy)

    out = {sym: [] for sym in symbols_n}
    if use_provider is None:
        return out

    for sym in symbols_n:
        try:
            out[sym] = list(use_provider.fetch(sym, state=state, policy=policy))
        except Exception:
            # Best-effort: never hard fail the run on a news fetch error.
            out[sym] = []
    return out


def score_news_sentiment_simple(
    items_by_symbol: Mapping[str, Sequence[NewsItem]],
    *,
    state: Dict[str, Any] | None = None,
    policy: Dict[str, Any] | None = None,
) -> Dict[str, float]:
    """Very small deterministic scorer (placeholder for LLM scorer).

    Returns a score in [-1, +1]. For now:
      - If state.mock_news_sentiment is present, use it (with default 0.0).
      - Else: returns 0.0 for all.
    """
    state = state or {}
    policy = policy or {}
    mock = state.get("mock_news_sentiment")
    out: Dict[str, float] = {}
    if isinstance(mock, dict):
        for sym in items_by_symbol.keys():
            try:
                out[sym] = float(mock.get(sym, 0.0))
            except Exception:
                out[sym] = 0.0
        return out
    return {sym: 0.0 for sym in items_by_symbol.keys()}
