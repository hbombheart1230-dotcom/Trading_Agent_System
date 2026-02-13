from __future__ import annotations

from typing import Dict

from libs.news.scorers.base import NewsScorer
from libs.news.scorers.simple import SimpleKeywordNewsScorer
from libs.news.scorers.llm import LLMNewsScorer


def get_scorer(name: str | None) -> NewsScorer:
    n = (name or "simple").strip().lower()
    if n in ("simple", "keyword", "keywords"):
        return SimpleKeywordNewsScorer()
    if n in ("llm", "gpt", "model"):
        return LLMNewsScorer()
    # default
    return SimpleKeywordNewsScorer()
