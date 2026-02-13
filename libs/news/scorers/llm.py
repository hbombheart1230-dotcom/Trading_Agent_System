from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping

from libs.news.models import NewsItem


@dataclass
class LLMNewsSentimentScorer:
    """
    LLM-based news sentiment scorer.

    Contract:
      score(items_by_symbol, state=..., policy=...) -> {symbol: float}
    Priority:
      1) state['mock_news_sentiment'] if provided (tests/DRY_RUN)
      2) fallback to simple keyword scoring (non-network)
      3) (later) actual OpenRouter/LLM call can be plugged in here
    """

    def score(
        self,
        items_by_symbol: Mapping[str, List[NewsItem]],
        *,
        state: Dict[str, Any],
        policy: Dict[str, Any],
    ) -> Dict[str, float]:
        # 1) test hook
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

        # 2) safe fallback: keyword scoring (no network)
        return _keyword_score(items_by_symbol)


def _keyword_score(items_by_symbol: Mapping[str, List[NewsItem]]) -> Dict[str, float]:
    """
    Very small heuristic scorer for offline/dev.
    Produces roughly [-1.0, +1.0].
    """
    pos = ["급등", "서프라이즈", "호재", "상승", "흑자", "최대", "신고가", "강세", "수주", "호황", "실적 개선", "턴어라운드"]
    neg = ["급락", "부진", "악재", "하락", "적자", "경고", "리콜", "불확실", "규제", "소송", "실적 부진", "쇼크"]

    scores: Dict[str, float] = {}
    for sym, items in items_by_symbol.items():
        s = 0.0
        n = 0
        for it in items or []:
            text = f"{it.title} {it.summary}".strip()
            if not text:
                continue
            n += 1
            lp = sum(1 for w in pos if w in text)
            ln = sum(1 for w in neg if w in text)
            s += (lp - ln)
        if n == 0:
            scores[sym] = 0.0
        else:
            # squash
            raw = s / max(1.0, float(n))
            if raw > 1.0:
                raw = 1.0
            if raw < -1.0:
                raw = -1.0
            scores[sym] = float(raw)
    return scores
