"""News collection + sentiment scoring (M18-3).

This module is intentionally lightweight to keep unit tests offline.

- In tests/DRY_RUN, inject:
    state['mock_news_items'] = [{'title':..., 'symbols':['005930',...], ...}, ...]
  or
    state['mock_news_sentiment'] = {'005930': +0.6, ...}

- Live: wire Naver/Google news collection and LLM scoring later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class NewsItem:
    title: str
    url: str = ""
    published_at: str = ""
    symbols: Optional[List[str]] = None


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def get_news_items_from_state(state: Dict[str, Any]) -> List[NewsItem]:
    raw = state.get("mock_news_items") or state.get("news_items") or []
    items: List[NewsItem] = []
    for it in raw:
        if isinstance(it, NewsItem):
            items.append(it)
            continue
        if not isinstance(it, dict):
            continue
        items.append(
            NewsItem(
                title=str(it.get("title") or ""),
                url=str(it.get("url") or ""),
                published_at=str(it.get("published_at") or ""),
                symbols=list(it.get("symbols") or []) if it.get("symbols") is not None else None,
            )
        )
    return items


def score_news_sentiment(
    state: Dict[str, Any],
    candidate_symbols: Iterable[str],
) -> Dict[str, float]:
    """Return per-symbol sentiment in [-1, +1].

    Priority:
      1) state['mock_news_sentiment'] dict (tests)
      2) derive naive scores from news_items if they include symbols
      3) default 0.0 for all candidates
    """
    candidates = [str(s) for s in candidate_symbols]

    if isinstance(state.get("mock_news_sentiment"), dict):
        out = {}
        for s in candidates:
            try:
                out[s] = _clamp(float(state["mock_news_sentiment"].get(s, 0.0)), -1.0, 1.0)
            except Exception:
                out[s] = 0.0
        return out

    items = get_news_items_from_state(state)
    if items:
        # naive: count positive/negative keywords; placeholder until LLM wired.
        pos_kw = ("호재", "상승", "급등", "수주", "흑자", "증가")
        neg_kw = ("악재", "하락", "급락", "적자", "감소", "리콜")
        by_sym = {s: 0.0 for s in candidates}
        for it in items:
            text = (it.title or "").lower()
            score = 0.0
            if any(k.lower() in text for k in pos_kw):
                score += 0.2
            if any(k.lower() in text for k in neg_kw):
                score -= 0.2
            syms = it.symbols or []
            for s in syms:
                s = str(s)
                if s in by_sym:
                    by_sym[s] = _clamp(by_sym[s] + score, -1.0, 1.0)
        return by_sym

    return {s: 0.0 for s in candidates}
