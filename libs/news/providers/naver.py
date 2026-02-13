from __future__ import annotations

from typing import Sequence, Dict, Any, List
import os

from .base import NewsItem


class NaverNewsProvider:
    """Placeholder provider for Naver Search API.

    Not implemented yet. Interface is batch-based: fetch(symbols=[...]).
    """

    name = "naver"

    def fetch(
        self,
        symbols: Sequence[str],
        *,
        state: Dict[str, Any] | None = None,
        policy: Dict[str, Any] | None = None,
    ) -> Sequence[NewsItem]:
        policy = policy or {}
        live = bool(policy.get("news_live")) or (os.getenv("NEWS_LIVE") == "1")
        if not live:
            return []
        # TODO: implement real Naver Search API
        return []
