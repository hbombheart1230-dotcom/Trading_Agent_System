from typing import Dict, List, Mapping

from libs.news.models import NewsItem


class SimpleNewsSentimentScorer:
    """
    M18 simple keyword-based sentiment scorer
    """

    POSITIVE = ["서프라이즈", "급등", "호재", "실적 개선", "상승"]
    NEGATIVE = ["부진", "급락", "악재", "적자", "하락"]

    def score(
        self,
        items_by_symbol: Mapping[str, List[NewsItem]],
        state=None,
        policy=None,
    ) -> Dict[str, float]:

        scores: Dict[str, float] = {}

        for symbol, items in items_by_symbol.items():
            total = 0.0

            for item in items:
                text = f"{item.title} {item.summary}"

                for p in self.POSITIVE:
                    if p in text:
                        total += 1.0

                for n in self.NEGATIVE:
                    if n in text:
                        total -= 1.0

            scores[symbol] = total

        return scores
