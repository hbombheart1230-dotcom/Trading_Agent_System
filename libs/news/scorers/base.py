from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Protocol, Sequence

from libs.news.providers.base import NewsItem


class NewsScorer(Protocol):
    """Scores news into per-symbol sentiment scores in [-1.0, +1.0]."""

    def score(self, items: Sequence[NewsItem], symbols: Sequence[str]) -> Dict[str, float]:
        ...
