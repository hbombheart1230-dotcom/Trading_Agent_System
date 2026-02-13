"""News scorer registry.

Scorers are pluggable modules that map (news items) -> sentiment scores.

Names:
- simple: keyword heuristic (or mock/state override)
- openrouter: LLM scorer via OpenRouter (M19-4)
"""

from __future__ import annotations

from typing import Any

from libs.news.scorers.simple import SimpleNewsSentimentScorer

try:
    from libs.news.scorers.llm import OpenRouterNewsSentimentScorer
except Exception:  # pragma: no cover
    OpenRouterNewsSentimentScorer = None  # type: ignore


def get_scorer(name: str | None) -> Any:
    key = (name or "simple").strip().lower()
    if key in ("simple", "heuristic"):
        return SimpleNewsSentimentScorer()
    if key in ("openrouter", "llm"):
        if OpenRouterNewsSentimentScorer is None:
            return SimpleNewsSentimentScorer()
        return OpenRouterNewsSentimentScorer()
    # default
    return SimpleNewsSentimentScorer()
