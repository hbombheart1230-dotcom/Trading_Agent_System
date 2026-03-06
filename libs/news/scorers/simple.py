from __future__ import annotations

import re
from typing import Dict, List, Mapping

from libs.news.models import NewsItem


class SimpleNewsSentimentScorer:
    """Simple keyword-based sentiment scorer.

    - Handles both Korean and English headlines.
    - Removes simple HTML tags returned by some providers (e.g. Naver `<b>...</b>`).
    - Returns score in [-1.0, +1.0] per symbol.
    """

    POSITIVE = [
        "급등",
        "상승",
        "호재",
        "실적 개선",
        "흑자",
        "수주",
        "신고가",
        "신기록",
        "최다",
        "호조",
        "강세",
        "최고",
        "성장",
        "surge",
        "rally",
        "gain",
        "beats",
        "beat",
        "upgrade",
        "record high",
        "profit",
    ]
    NEGATIVE = [
        "급락",
        "하락",
        "악재",
        "실적 부진",
        "적자",
        "의혹",
        "강요",
        "부당",
        "소송",
        "리스크",
        "신저가",
        "약세",
        "downgrade",
        "misses",
        "miss",
        "plunge",
        "drop",
        "fall",
        "loss",
    ]

    _HTML_TAG_RE = re.compile(r"<[^>]+>")

    @classmethod
    def _normalize(cls, text: str) -> str:
        cleaned = cls._HTML_TAG_RE.sub(" ", str(text or ""))
        cleaned = cleaned.replace("&nbsp;", " ").replace("&amp;", "&")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned.lower()

    def score(
        self,
        items_by_symbol: Mapping[str, List[NewsItem]],
        state=None,
        policy=None,
    ) -> Dict[str, float]:
        scores: Dict[str, float] = {}

        for symbol, items in items_by_symbol.items():
            total = 0.0
            seen = 0

            for item in items:
                text = self._normalize(f"{item.title} {item.summary}")
                if not text:
                    continue
                seen += 1

                for p in self.POSITIVE:
                    if p.lower() in text:
                        total += 1.0

                for n in self.NEGATIVE:
                    if n.lower() in text:
                        total -= 1.0

            if seen <= 0:
                scores[symbol] = 0.0
                continue

            # Keep score stable and bounded for downstream consumers.
            norm = total / max(1.0, float(seen) * 2.0)
            if norm > 1.0:
                norm = 1.0
            if norm < -1.0:
                norm = -1.0
            scores[symbol] = float(norm)

        return scores
