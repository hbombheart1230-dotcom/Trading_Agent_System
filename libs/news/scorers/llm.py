from __future__ import annotations

from typing import Dict, Sequence

from libs.news.providers.base import NewsItem


class LLMNewsScorer:
    """LLM-based scorer stub.

    - In DRY_RUN / tests you should inject `mock_news_sentiment` in state and bypass this.
    - In LIVE this can call your preferred LLM endpoint later.
    """

    def __init__(self, model: str | None = None):
        self.model = model or "stub-llm"

    def score(self, items: Sequence[NewsItem], symbols: Sequence[str]) -> Dict[str, float]:
        # Keep deterministic safe default until real integration.
        return {s: 0.0 for s in symbols}
