from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping

from libs.news.models import NewsItem
from libs.news.scorers.simple import SimpleNewsSentimentScorer


@dataclass
class LLMNewsSentimentScorer:
    """LLM-oriented news sentiment scorer.

    Current behavior:
    1) If `state['mock_news_sentiment']` exists, return that (test/stub hook).
    2) Otherwise fallback to `SimpleNewsSentimentScorer` (offline-safe).
    """

    def score(
        self,
        items_by_symbol: Mapping[str, List[NewsItem]],
        *,
        state: Dict[str, Any],
        policy: Dict[str, Any],
    ) -> Dict[str, float]:
        mock = state.get("mock_news_sentiment")
        if isinstance(mock, dict):
            out: Dict[str, float] = {}
            for sym in items_by_symbol.keys():
                v = mock.get(sym, 0.0)
                try:
                    out[sym] = float(v)
                except Exception:
                    out[sym] = 0.0
            return out

        return SimpleNewsSentimentScorer().score(items_by_symbol, state=state, policy=policy)
