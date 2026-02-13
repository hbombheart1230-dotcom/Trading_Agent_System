from __future__ import annotations

from typing import Sequence, Dict, Any
import os

from .base import NewsItem, NewsProvider


class NaverNewsProvider:
    """Placeholder provider for Naver Search API.

    Not implemented yet. We keep the interface so Strategist can swap providers
    without refactoring downstream scoring.

    Policy knobs (reserved):
      - news_live: bool (or env NEWS_LIVE=1)
      - naver_client_id / naver_client_secret
      - naver_endpoint
    """

    name = "naver"

    def fetch(self, symbol: str, *, state: Dict[str, Any] | None = None, policy: Dict[str, Any] | None = None) -> Sequence[NewsItem]:
        policy = policy or {}
        live = bool(policy.get("news_live")) or (os.getenv("NEWS_LIVE") == "1")
        if not live:
            return []
        return []
