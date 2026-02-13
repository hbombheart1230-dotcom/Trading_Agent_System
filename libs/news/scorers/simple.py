from __future__ import annotations

import re
from typing import Dict, Sequence

from libs.news.providers.base import NewsItem
from libs.news.scorers.base import NewsScorer


class SimpleKeywordNewsScorer:
    """A tiny deterministic scorer for tests and early-stage runs.

    Heuristic:
    - Count positive/negative keywords in title+summary.
    - Aggregate per symbol by averaging matched item scores.
    - Clamp into [-1, +1].

    This is intentionally simple and dependency-free.
    """

    POS = (
        "호재", "상승", "급등", "실적", "서프라이즈", "강세", "상향", "매수", "기대", "호황",
        "beat", "surge", "up", "upgrade", "record", "strong", "bullish",
    )
    NEG = (
        "악재", "하락", "급락", "실망", "부진", "약세", "하향", "매도", "우려", "불황",
        "miss", "plunge", "down", "downgrade", "weak", "bearish", "risk",
    )

    def _item_score(self, text: str) -> float:
        t = text.lower()
        pos = sum(1 for w in self.POS if w.lower() in t)
        neg = sum(1 for w in self.NEG if w.lower() in t)
        if pos == 0 and neg == 0:
            return 0.0
        # scale by net keywords, soften saturation
        raw = (pos - neg) / max(pos + neg, 1)
        # clamp
        return max(-1.0, min(1.0, raw))

    def score(self, items: Sequence[NewsItem], symbols: Sequence[str]) -> Dict[str, float]:
        # Default 0.0 for all symbols
        out: Dict[str, float] = {s: 0.0 for s in symbols}

        # bucket scores per symbol
        buckets: Dict[str, list[float]] = {s: [] for s in symbols}
        for it in items:
            text = f"{it.title} {it.summary or ''}"
            sc = self._item_score(text)
            # if provider already tagged symbol, use it; else try naive match
            if it.symbol and it.symbol in buckets:
                buckets[it.symbol].append(sc)
            else:
                for s in symbols:
                    if s and s in text:
                        buckets[s].append(sc)

        for s, arr in buckets.items():
            if arr:
                out[s] = max(-1.0, min(1.0, sum(arr) / len(arr)))
        return out
