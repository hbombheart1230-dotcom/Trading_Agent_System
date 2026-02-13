"""LLM-based news sentiment scorer.

This scorer is designed for OpenRouter but accessed through libs.llm.LLMRouter,
so the provider can be swapped later.

Contract:
- Input: items_by_symbol: dict[str, list[NewsItem]]
- Output: dict[str, float] in [-1, 1]

Safety:
- If DRY_RUN=1 OR no OpenRouter key configured -> returns 0.0s (unless mock provided)
- If state contains mock_news_sentiment -> uses it (test-first)
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict
from typing import Any, Dict, List, Mapping

from libs.llm.llm_router import LLMRouter

try:
    from libs.news.providers.base import NewsItem
except Exception:  # pragma: no cover
    NewsItem = Any  # type: ignore


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def _default_for_symbols(symbols: List[str], value: float = 0.0) -> Dict[str, float]:
    return {str(s): float(value) for s in symbols}


_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class OpenRouterNewsSentimentScorer:
    """Scores sentiment using an LLM via OpenRouter."""

    def __init__(self, router: LLMRouter | None = None):
        self.router = router or LLMRouter.from_env()

    def score(self, items_by_symbol: Mapping[str, List[NewsItem]], *, state: Dict[str, Any], policy: Dict[str, Any]) -> Dict[str, float]:
        symbols = [str(s) for s in items_by_symbol.keys()]

        # 1) mock override (tests)
        if isinstance(state.get("mock_news_sentiment"), dict):
            out = _default_for_symbols(symbols, 0.0)
            for k, v in state["mock_news_sentiment"].items():
                if str(k) in out:
                    try:
                        out[str(k)] = _clamp(float(v))
                    except Exception:
                        pass
            return out

        # 2) DRY_RUN / missing key: do not call network
        if os.getenv("DRY_RUN", "0").strip() == "1":
            return _default_for_symbols(symbols, 0.0)
        if self.router.client is None:
            return _default_for_symbols(symbols, 0.0)

        # 3) LLM scoring (best-effort)
        topn = int(policy.get("news_topn_per_symbol") or 5)
        role = str(policy.get("news_llm_role") or "NEWS_SCORER")

        scores: Dict[str, float] = {}
        for sym in symbols:
            items = list(items_by_symbol.get(sym) or [])[:topn]
            scores[sym] = self._score_one(sym, items, role=role, policy=policy)

        # ensure defaults
        for sym in symbols:
            scores.setdefault(sym, 0.0)
        return scores

    def _score_one(self, symbol: str, items: List[NewsItem], *, role: str, policy: Dict[str, Any]) -> float:
        if not items:
            return 0.0

        # compact context: titles + summaries
        lines: List[str] = []
        for it in items:
            try:
                title = getattr(it, "title", None) or (it.get("title") if isinstance(it, dict) else "")
                summary = getattr(it, "summary", None) or (it.get("summary") if isinstance(it, dict) else "")
                source = getattr(it, "source", None) or (it.get("source") if isinstance(it, dict) else "")
                lines.append(f"- [{source}] {title} :: {summary}".strip())
            except Exception:
                continue

        system = (
            "You are a financial news sentiment analyst. "
            "Given recent headlines about a single Korean stock, output a JSON object with a single key 'sentiment'. "
            "The value must be a number between -1 and 1 where -1 is very negative, 0 is neutral, 1 is very positive. "
            "Do not include any other keys."
        )
        user = (
            f"Stock symbol: {symbol}\n"
            "Recent news (most recent first):\n"
            + "\n".join(lines)
            + "\n\nReturn JSON only."
        )

        # allow scorer-specific overrides
        llm_policy = {
            "temperature": float(policy.get("news_llm_temperature") or 0.0),
            "max_tokens": int(policy.get("news_llm_max_tokens") or 64),
        }
        text = self.router.chat(role=role, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], policy=llm_policy)
        return _parse_sentiment(text)


def _parse_sentiment(text: str) -> float:
    if not isinstance(text, str) or not text.strip():
        return 0.0

    # try to find JSON object anywhere in the output
    m = _JSON_RE.search(text)
    candidate = m.group(0) if m else text
    try:
        obj = json.loads(candidate)
        val = obj.get("sentiment")
        return _clamp(float(val))
    except Exception:
        # fallback: look for a number
        nums = re.findall(r"-?\d+(?:\.\d+)?", text)
        if nums:
            try:
                return _clamp(float(nums[0]))
            except Exception:
                return 0.0
        return 0.0
